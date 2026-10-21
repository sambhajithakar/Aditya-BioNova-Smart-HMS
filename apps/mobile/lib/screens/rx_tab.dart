/// Rx tab (doctor): write a prescription draft with no network, from the
/// cached **validated drug catalog** — never free-text medication.
///
/// Drafts land in the outbox like any other mutation and are listed here
/// with their sync state. **Signing is deliberately online-only**: the
/// server owns the blocking allergy check and the `prescription.sign`
/// permission, so the sign button appears only once the server has
/// accepted the draft (its id arrives through the sync engine's id map).
/// An offline draft can therefore never become a signed prescription.
///
/// Rural Clinic mode adds one-tap chips for the common frequencies (the
/// standard OD / BD / TDS / QID / HS / SOS codes, with their meaning in the
/// UI language as a tooltip) and durations, so a dose is the only thing
/// that still needs typing. The chips only fill the same fields; the draft,
/// its dedupe key and the sync path are unchanged.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../data/directory.dart';
import '../l10n/l10n.dart';
import '../settings/app_settings.dart';
import '../sync/outbox.dart';
import '../util/dates.dart';
import '../pdf/documents.dart';
import 'sync_widgets.dart';
import 'widgets.dart';

/// Frequency codes offered as quick picks (kept untranslated, as written
/// on prescriptions).
const List<String> kQuickFrequencies = ['OD', 'BD', 'TDS', 'QID', 'HS', 'SOS'];

/// Durations (days) offered as quick picks.
const List<int> kQuickDurations = [3, 5, 7, 10, 14, 30];

String frequencyMeaning(AppLocalizations l, String code) => switch (code) {
      'OD' => l.freqOD,
      'BD' => l.freqBD,
      'TDS' => l.freqTDS,
      'QID' => l.freqQID,
      'HS' => l.freqHS,
      'SOS' => l.freqSOS,
      _ => code,
    };

class RxTab extends StatefulWidget {
  const RxTab({
    super.key,
    required this.graph,
    this.showDispenseQuantity = true,
  });

  final AppGraph graph;

  /// False when the server reports no `pharmacy` feature: there is no
  /// dispensing to cap, so the optional quantity field is hidden.
  final bool showDispenseQuantity;

  @override
  State<RxTab> createState() => _RxTabState();
}

class _RxTabState extends State<RxTab> {
  String? _patientId;
  String? _drugId;
  final _diagnosis = TextEditingController();
  final _dose = TextEditingController();
  final _frequency = TextEditingController();
  final _duration = TextEditingController(text: '5');
  final _dispenseQty = TextEditingController();
  final List<Map<String, dynamic>> _items = <Map<String, dynamic>>[];
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    _patientId =
        widget.graph.directory.resolveSelection(null, widget.graph.idMap);
    final drugs = widget.graph.directory.drugs;
    _drugId = drugs.isNotEmpty ? drugs.first['id'] as String? : null;
    _adopt();
    widget.graph.network.addListener(_networkChanged);
  }

  @override
  void dispose() {
    widget.graph.network.removeListener(_networkChanged);
    _diagnosis.dispose();
    _dose.dispose();
    _frequency.dispose();
    _duration.dispose();
    _dispenseQty.dispose();
    super.dispose();
  }

  Future<void> _adopt() async {
    await widget.graph.drafts.adoptSynced(widget.graph.idMap);
    if (mounted) setState(() {});
  }

  Future<void> _refreshCatalog() async {
    try {
      final drugs = await widget.graph.client.request('GET', '/prescriptions/drugs');
      if (drugs is! List) return;
      await widget.graph.directory.replaceDrugs(DirectoryCache.listOf(drugs));
      if (!mounted) return;
      setState(() {
        final items = widget.graph.directory.drugs;
        _drugId ??= items.isNotEmpty ? items.first['id'] as String? : null;
      });
    } catch (_) {
      // Offline: the cached catalog still works.
    }
  }

  /// Never a raw device id: server id, or `$ref:` until it syncs (H24).
  String _patientRef(String id) =>
      widget.graph.directory.refFor(id, widget.graph.idMap);

  void _addItem() {
    final drugId = _drugId;
    if (drugId == null) {
      setState(() => _error = context.l10n.rxNoCatalog);
      return;
    }
    final dose = _dose.text.trim();
    final frequency = _frequency.text.trim();
    final duration = int.tryParse(_duration.text.trim()) ?? 0;
    if (dose.isEmpty || frequency.isEmpty || duration < 1) {
      setState(() => _error = context.l10n.rxRequired);
      return;
    }
    // Optional units to dispense (API: 1..10000). Blank = not specified.
    final qtyText = _dispenseQty.text.trim();
    final dispenseQty = qtyText.isEmpty ? null : int.tryParse(qtyText);
    if (qtyText.isNotEmpty &&
        (dispenseQty == null || dispenseQty < 1 || dispenseQty > 10000)) {
      setState(() => _error = context.l10n.rxDispenseRange);
      return;
    }
    final drug = widget.graph.directory.drugs.firstWhere(
      (d) => d['id'] == drugId,
      orElse: () => <String, dynamic>{'id': drugId, 'generic_name': drugId},
    );
    setState(() {
      _error = null;
      _items.add({
        'drug_id': drugId,
        'drug_name': (drug['generic_name'] as String?) ?? drugId,
        'dose': dose,
        'route': 'oral',
        'frequency': frequency,
        'duration_days': duration,
        'dispense_quantity': ?dispenseQty,
      });
      _dose.clear();
      _frequency.clear();
      _dispenseQty.clear();
    });
  }

  Future<void> _saveDraft() async {
    final patientId =
        widget.graph.directory.resolveSelection(_patientId, widget.graph.idMap);
    if (patientId == null) {
      setState(() => _error = context.l10n.pickPatientFirst);
      return;
    }
    if (_items.isEmpty) {
      setState(() => _error = context.l10n.rxAddOne);
      return;
    }

    final localRef = Outbox.newId();
    final op = widget.graph.outbox.enqueue(
      entity: 'prescription',
      method: 'POST',
      path: '/prescriptions',
      payload: {
        'patient_id': _patientRef(patientId),
        'diagnosis_text': _diagnosis.text.trim(),
        'items': [
          for (final item in _items)
            {
              'drug_id': item['drug_id'],
              'dose': item['dose'],
              'route': item['route'],
              'frequency': item['frequency'],
              'duration_days': item['duration_days'],
              if (item['dispense_quantity'] != null)
                'dispense_quantity': item['dispense_quantity'],
            },
        ],
      },
      // D11: the whole regimen (drug, dose, frequency, days, quantity) on
      // the local day — a corrected dose is a NEW draft, a double-tap is not.
      dedupeKey: 'rx:$patientId:${localDay()}:${_items.map((i) => [
            i['drug_id'],
            i['dose'],
            i['frequency'],
            i['duration_days'],
            i['dispense_quantity'] ?? '',
          ].join('/')).join(',')}',
      localRef: localRef,
    );

    if (op.localRef != localRef) {
      setState(() {
        _error = null;
        _notice = context.l10n.rxDuplicate;
      });
      return;
    }

    await widget.graph.drafts.addDraft(
      localRef: localRef,
      patientRef: _patientRef(patientId),
      patientLabel: widget.graph.directory.patientLabel(patientId),
      diagnosis: _diagnosis.text.trim(),
      items: List<Map<String, dynamic>>.of(_items),
    );
    if (!mounted) return;
    setState(() {
      _error = null;
      _notice = context.l10n.rxSaved;
      _items.clear();
      _diagnosis.clear();
    });
    widget.graph.scheduler.requestSync();
  }

  Future<void> _sign(String localRef, String serverId) async {
    setState(() => _error = null);
    try {
      await widget.graph.client
          .request('POST', '/prescriptions/$serverId/sign');
      await widget.graph.drafts.markSigned(localRef);
      if (!mounted) return;
      setState(() => _notice = context.l10n.rxSigned);
    } catch (err) {
      if (!mounted) return;
      setState(() => _error = err.toString());
    }
  }

  String get _clinic =>
      widget.graph.session.cachedProfile?.organizationName ?? '';

  /// DRAFT preview — watermarked, generated on the device.
  Future<void> _previewPdf(Map<String, dynamic> draft) async {
    try {
      final bytes = await buildRxDraftPdf(
        draft: draft,
        clinicName: _clinic,
        prescriber: widget.graph.session.cachedProfile?.fullName ?? '',
      );
      await widget.graph.pdfOutput.share(bytes, 'rx-draft.pdf');
      if (mounted) setState(() => _notice = context.l10n.rxDraftPdfDone);
    } catch (err) {
      if (mounted) setState(() => _error = err.toString());
    }
  }

  /// Signed prescription — built ONLY from the server's record.
  Future<void> _printSigned(String serverId) async {
    try {
      final rx = await widget.graph.client.getPrescription(serverId);
      final bytes = await buildSignedRxPdf(serverRx: rx, clinicName: _clinic);
      await widget.graph.pdfOutput.share(bytes, 'rx-$serverId.pdf');
    } catch (err) {
      if (mounted) setState(() => _error = err.toString());
    }
  }

  void _networkChanged() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final directory = widget.graph.directory;
    final drafts = widget.graph.drafts.drafts;
    final l = context.l10n;
    final rural = widget.graph.settings.ruralMode;
    final itemHeight =
        rural ? kRuralTouchTarget + 8 : kMinInteractiveDimension;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(l.rxTitle,
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            TextButton.icon(
              onPressed: () async {
                await _refreshCatalog();
                await _adopt();
              },
              icon: const Icon(Icons.refresh, size: 18),
              label: Text(l.refresh),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Text(l.patient, style: Theme.of(context).textTheme.labelLarge),
        DropdownButton<String>(
          key: const Key('rx-patient'),
          isExpanded: true,
          itemHeight: itemHeight,
          value: directory.resolveSelection(_patientId, widget.graph.idMap),
          hint: const Text('—'),
          items: [
            for (final p in directory.patients)
              DropdownMenuItem<String>(
                value: p['id'] as String,
                child: Text(directory.pickerLabel(p, widget.graph.idMap,
                    pendingTag: l.pendingSyncTag, syncedTag: l.syncedTag)),
              ),
          ],
          onChanged: (v) => setState(() => _patientId = v),
        ),
        const SizedBox(height: 12),
        Text(l.rxMedicine, style: Theme.of(context).textTheme.labelLarge),
        DropdownButton<String>(
          key: const Key('rx-drug'),
          isExpanded: true,
          itemHeight: itemHeight,
          value: _drugId,
          hint: const Text('—'),
          items: [
            for (final d in directory.drugs)
              DropdownMenuItem<String>(
                value: d['id'] as String,
                child: Text((d['generic_name'] as String?) ?? ''),
              ),
          ],
          onChanged: (v) => setState(() => _drugId = v),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('rx-dose'),
                controller: _dose,
                decoration: InputDecoration(labelText: l.rxDose),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                key: const Key('rx-frequency'),
                controller: _frequency,
                decoration: InputDecoration(labelText: l.rxFrequency),
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: rural ? 96 : 80,
              child: TextField(
                key: const Key('rx-duration'),
                controller: _duration,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(labelText: l.rxDays),
              ),
            ),
          ],
        ),
        if (rural) ..._quickPicks(l),
        if (widget.showDispenseQuantity)
          TextField(
            key: const Key('rx-dispense-qty'),
            controller: _dispenseQty,
            keyboardType: TextInputType.number,
            decoration: InputDecoration(
              labelText: l.rxDispense,
              helperText: l.rxDispenseHelp,
            ),
          ),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            key: const Key('rx-add-item'),
            onPressed: _addItem,
            icon: const Icon(Icons.add, size: 18),
            label: Text(l.rxAddItem),
          ),
        ),
        for (final item in _items)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.medication_outlined, size: 18),
            title: Text(
              l.rxItemLine(
                    '${item['drug_name']}',
                    '${item['dose']}',
                    '${item['frequency']}',
                    '${item['duration_days']}',
                  ) +
                  (item['dispense_quantity'] != null
                      ? l.rxItemDispense('${item['dispense_quantity']}')
                      : ''),
            ),
          ),
        TextField(
          key: const Key('rx-diagnosis'),
          controller: _diagnosis,
          decoration: InputDecoration(labelText: l.rxDiagnosis),
        ),
        const SizedBox(height: 12),
        FilledButton(
          key: const Key('rx-save'),
          onPressed: _saveDraft,
          child: Text(l.rxSave),
        ),
        if (_notice != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_notice!, key: const Key('rx-notice')),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              _error!,
              key: const Key('rx-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        const SizedBox(height: 20),
        Text(l.rxDrafts, style: Theme.of(context).textTheme.titleSmall),
        for (final draft in drafts) _draftCard(draft),
        if (drafts.isEmpty)
          Text(
            l.rxNoDrafts,
            style: Theme.of(context).textTheme.bodySmall,
          ),
      ],
    );
  }

  /// Rural Clinic mode: one tap fills frequency / days.
  List<Widget> _quickPicks(AppLocalizations l) => [
        const SizedBox(height: 8),
        Text(l.rxQuickFrequency, style: Theme.of(context).textTheme.labelLarge),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            for (final code in kQuickFrequencies)
              QuickPickChip(
                key: Key('rx-freq-$code'),
                label: code,
                tooltip: frequencyMeaning(l, code),
                selected: _frequency.text.trim() == code,
                onSelected: () => setState(() => _frequency.text = code),
              ),
          ],
        ),
        const SizedBox(height: 8),
        Text(l.rxQuickDuration, style: Theme.of(context).textTheme.labelLarge),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            for (final days in kQuickDurations)
              QuickPickChip(
                key: Key('rx-days-$days'),
                label: l.daysCount(days),
                selected: _duration.text.trim() == '$days',
                onSelected: () => setState(() => _duration.text = '$days'),
              ),
          ],
        ),
      ];

  Widget _draftCard(Map<String, dynamic> draft) {
    final l = context.l10n;
    final localRef = draft['localRef'] as String? ?? '';
    final serverId = draft['serverId'] as String?;
    final signed = draft['signed'] == true;
    final op = widget.graph.outbox.creatorOf(localRef);
    final conflicted = op?.status == OpStatus.conflicted;
    final pending = op != null && !conflicted;
    // D17: no op AND no server id means the draft was discarded — it was
    // never sent and must not read "Synced".
    final synced = op == null && serverId != null;
    final discarded = draft['discarded'] == true || (op == null && !synced);
    final offline = widget.graph.network.value.isOffline;

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${draft['patientLabel'] ?? ''} — ${draft['diagnosis'] ?? ''}'
                  .trim(),
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 4),
            Text(
              [
                for (final item in (draft['items'] as List<dynamic>? ?? const []))
                  l.rxDraftLine(
                        '${item['drug_name']}',
                        '${item['dose']}',
                        '${item['frequency']}',
                        '${item['duration_days']}',
                      ) +
                      (item['dispense_quantity'] != null
                          ? ' ×${item['dispense_quantity']}'
                          : ''),
              ].join('\n'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                if (signed)
                  StateChip(
                      label: l.stateSigned,
                      tone: Theme.of(context).colorScheme.primary)
                else if (conflicted)
                  StateChip(
                      label: l.stateConflict, tone: const Color(0xFFB3261E))
                else if (pending)
                  StateChip(
                      label: l.stateSavedPending,
                      tone: const Color(0xFF0B5D8A))
                else if (discarded)
                  StateChip(
                      label: l.stateDiscarded, tone: const Color(0xFF6B6B6B))
                else
                  StateChip(
                      label: l.stateSynced, tone: const Color(0xFF1B7F5A)),
                const Spacer(),
                if (!signed && !discarded)
                  TextButton(
                    key: Key('rx-sign-$localRef'),
                    onPressed: (serverId != null && !pending && !offline)
                        ? () => _sign(localRef, serverId)
                        : null,
                    child: Text(pending || serverId == null
                        ? l.rxSignAfterSync
                        : l.rxSign),
                  ),
              ],
            ),
            if (!signed && !discarded && offline)
              Text(
                l.needsConnection,
                key: Key('rx-sign-offline-$localRef'),
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: Theme.of(context).colorScheme.error),
              ),
            Wrap(children: [
              if (!signed && !discarded)
                TextButton.icon(
                  key: Key('rx-pdf-$localRef'),
                  onPressed: () => _previewPdf(draft),
                  icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
                  label: Text(l.rxDraftPdf),
                ),
              if (signed && serverId != null)
                OnlineOnlyButton(
                  key: Key('rx-print-$localRef'),
                  network: widget.graph.network,
                  icon: Icons.print_outlined,
                  label: l.rxPrintSigned,
                  onPressed: () => _printSigned(serverId),
                ),
            ]),
          ],
        ),
      ),
    );
  }
}
