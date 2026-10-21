/// Patients tab: authorised cached lookup + online search.
///
/// Offline it searches ONLY the bounded, encrypted cache of patients this
/// user already fetched online (see `DirectoryCache`); online, "Search
/// server" asks `GET /patients?q=` (the server applies its own permission
/// checks) and remembers the results in the bounded cache. The list is a
/// lazy `ListView.builder`: 2,000 rows cost what is on screen.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../data/directory.dart';
import '../l10n/l10n.dart';

class PatientsTab extends StatefulWidget {
  const PatientsTab({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<PatientsTab> createState() => _PatientsTabState();
}

class _PatientsTabState extends State<PatientsTab> {
  final _query = TextEditingController();
  List<Map<String, dynamic>> _results = const [];
  String? _error;
  bool _searching = false;

  @override
  void initState() {
    super.initState();
    _results = widget.graph.directory.patients;
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  void _local(String q) {
    setState(() => _results = widget.graph.directory.search(q));
  }

  Future<void> _server() async {
    final q = _query.text.trim();
    if (q.length < 2) return;
    setState(() {
      _searching = true;
      _error = null;
    });
    try {
      final page = await widget.graph.client.searchPatients(q);
      final items = DirectoryCache.listOf(page['items']);
      await widget.graph.directory.rememberFetched(items);
      if (!mounted) return;
      setState(() => _results = widget.graph.directory.search(q));
    } catch (_) {
      if (mounted) setState(() => _error = context.l10n.needsConnection);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final idMap = widget.graph.idMap;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: TextField(
            key: const Key('patients-search'),
            controller: _query,
            onChanged: _local,
            onSubmitted: (_) => _server(),
            decoration: InputDecoration(
              labelText: l.patientsSearch,
              suffixIcon: IconButton(
                key: const Key('patients-search-server'),
                tooltip: l.patientsSearchServer,
                icon: _searching
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.cloud_download_outlined),
                onPressed: _searching ? null : _server,
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Text(
            _error ?? l.patientsCachedNote(_results.length),
            key: const Key('patients-note'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
        Expanded(
          child: ListView.builder(
            key: const Key('patients-list'),
            itemCount: _results.length,
            itemExtent: 64,
            itemBuilder: (context, i) {
              final p = _results[i];
              return ListTile(
                key: Key('patient-row-${p['id']}'),
                title: Text(widget.graph.directory.pickerLabel(p, idMap,
                    pendingTag: l.pendingSyncTag, syncedTag: l.syncedTag)),
                subtitle: Text([
                  genderLabel(l, '${p['gender'] ?? ''}'),
                  if ('${p['phone'] ?? ''}'.isNotEmpty) '${p['phone']}',
                ].join(' · ')),
              );
            },
          ),
        ),
      ],
    );
  }
}
