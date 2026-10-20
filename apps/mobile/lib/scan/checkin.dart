/// Clinic check-in by QR code.
///
/// The QR shown at the clinic desk (or on a patient's appointment slip)
/// carries an **opaque token** — no name, no UHID, no phone: the server
/// resolves it. The device never interprets the token; it validates only
/// its shape and queues one check-in request, so check-in works offline
/// and syncs like any other op (same Idempotency-Key on every replay).
///
/// TODO(api, check-in workstream): the endpoint does not exist in this
/// worktree yet. Contract the mobile client is written against:
///
/// ```text
/// POST /api/v1/opd/check-in
///   headers: Authorization: Bearer …, Idempotency-Key: <client op id>
///   body:    {"token": "<opaque>", "branch_id": "<uuid|null>"}
///   201  QueueEntryOut            (patient checked into today's queue)
///   200  QueueEntryOut            (already checked in today — idempotent,
///                                  NOT a 409, so a replay is not a conflict)
///   404  {"detail": "Unknown check-in code"}
///   410  {"detail": "Check-in code expired"}
///   422  validation error
/// permission: queue.manage; tenant-scoped; audited.
/// ```
///
/// Until the server reports the `qr_checkin` feature the scan button stays
/// hidden (see `FeatureKeys.qrCheckin`), so no request is ever sent to a
/// server that cannot answer it.
library;

import '../sync/outbox.dart';
import '../util/dates.dart';

/// Path of the check-in endpoint (see the contract above).
const String kCheckInPath = '/opd/check-in';

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
        payload: {'token': token, 'branch_id': branchId},
        dedupeKey: 'checkin:$token:${localDay()}',
      );
}
