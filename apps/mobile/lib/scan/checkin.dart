/// Clinic check-in by QR code.
///
/// The QR shown at the clinic desk (or on a patient's appointment slip)
/// carries an **opaque token** — no name, no UHID, no phone: the server
/// resolves it. The device never interprets the token; it validates only
/// its shape and queues one check-in request, so check-in works offline
/// and syncs like any other op (same Idempotency-Key on every replay).
///
/// Server contract (apps/api/app/routers/checkin.py, migration 0015):
///
/// ```text
/// POST /api/v1/checkin/confirm
///   body:    {"code": "<opaque base32 code from the QR>"}
///   200  {"status": "checked_in" | "already_checked_in", "appointment_id",
///         "queue_entry": {...token_number...}}   (idempotent: a replay or a
///                                                 second scan is not a conflict)
///   404  unknown code, or a code of another clinic (indistinguishable)
///   410  code expired or replaced
///   409  appointment cancelled / completed / not today
/// permission: checkin.manage; feature: opd_queue; rate-limited; audited.
/// ```
///
/// The scan button is shown only when the server explicitly reports the
/// `opd_queue` feature AND the `checkin.manage` permission, so no request is
/// ever sent to a server that cannot answer it.
library;

import '../sync/outbox.dart';
import '../util/dates.dart';

/// Path of the check-in endpoint (see the contract above).
const String kCheckInPath = '/checkin/confirm';

abstract final class CheckInToken {
  /// Opaque URL-safe token: 16–512 chars of `A-Z a-z 0-9 - _ . ~`.
  static final RegExp _shape = RegExp(r'^[A-Za-z0-9\-_.~]{16,512}$');

  /// Extract the token from the scanned text: the bare token, or a link
  /// such as `https://<host>/c/<token>` / `hms://checkin?t=<token>`.
  /// Returns null for anything else (e.g. a random product barcode).
  static String? parse(String scanned) {
    final raw = scanned.trim();
    if (_shape.hasMatch(raw)) return raw;
    final uri = Uri.tryParse(raw);
    if (uri == null || !uri.hasScheme) return null;
    final fromQuery = uri.queryParameters['t'] ?? uri.queryParameters['token'];
    if (fromQuery != null && _shape.hasMatch(fromQuery)) return fromQuery;
    if (uri.pathSegments.isNotEmpty) {
      final last = uri.pathSegments.last;
      if (_shape.hasMatch(last)) return last;
    }
    return null;
  }
}

/// Queues check-in requests (offline-capable) behind an interface, so the
/// screens and tests do not depend on the endpoint's final shape.
abstract interface class CheckInClient {
  /// Returns the op (an existing one when the same code was already
  /// scanned today — duplicate prevention).
  OutboxOp enqueue(String token, {String? branchId});
}

class OutboxCheckInClient implements CheckInClient {
  OutboxCheckInClient(this.outbox);

  final Outbox outbox;

  @override
  OutboxOp enqueue(String token, {String? branchId}) => outbox.enqueue(
        entity: 'check_in',
        method: 'POST',
        path: kCheckInPath,
        payload: {'code': token},
        dedupeKey: 'checkin:$token:${localDay()}',
      );
}
