/// Device revocation (multi-device sessions).
///
/// The API exposes the existing session semantics (`GET /auth/sessions`,
/// `POST /auth/sessions/{id}/revoke`, `POST /auth/sessions/revoke-others`,
/// an admin's `POST /members/{id}/sessions/revoke`, member suspension,
/// refresh-token reuse detection). A revoked session shows up on the device
/// as:
///
/// * an authenticated call answered `401 "Session is no longer valid"` (the
///   access JWT is still unexpired but its session row is revoked) or
///   `401 "Account is not active"`, followed by a refused refresh; or
/// * `POST /auth/refresh` answered `403 "Membership is not active"` /
///   `"Organization is not active"`.
///
/// A plain expiry is different: the access JWT expired (`401 "Invalid or
/// expired token"`) and only the refresh is refused (idle/absolute cap).
/// That keeps the M7.0 behaviour (banner, offline work continues, sign in
/// again). Known ambiguity, resolved in the fail-safe direction: if the
/// refresh session hits its absolute cap while an access token is still
/// valid, the device takes the revocation path (PHI wiped, drafts kept).
///
/// On revocation the graph (see `AppGraph.handleRevocation`):
/// 1. halts the sync engine and the scheduler (nothing more is sent);
/// 2. wipes tokens, the app PIN and every cached server record (patients,
///    drug catalog, branches, synced drafts) — PHI the device no longer has
///    the right to show;
/// 3. MOVES every unsynced item (outbox ops, offline registrations, Rx /
///    consultation / appointment drafts, stock counts) out of the live
///    sections into a sealed `quarantine` section — still AES-256-GCM
///    encrypted at rest like the rest of the store, but unreachable from
///    any screen;
/// 4. shows "This device was signed out by an administrator".
///
/// Only when the SAME user (same user id AND organisation) signs in again
/// online is the quarantine released back into the live sections and synced
/// (each op with its original Idempotency-Key). Anyone else sees only a
/// count and may explicitly discard it after their own online sign-in.
library;

import '../store/local_store.dart';

enum SessionEnd {
  /// Refresh refused after a normal access-token expiry: sign in again,
  /// offline work continues meanwhile.
  expired,

  /// The session was revoked server-side (admin, user from another device,
  /// suspension, token-reuse detection): lock the device down.
  revoked,
}

/// Access-token 401 details that mean "your session row is dead".
const Set<String> kRevokedAccessDetails = {
  'Session is no longer valid',
  'Account is not active',
};

/// Refresh refusals that only happen to a revoked / suspended membership.
const Set<String> kRevokedRefreshDetails = {
  'Membership is not active',
  'Organization is not active',
};

/// Decide how a session ended once the refresh was refused.
///
/// [lastAccessDenial] is the detail of the most recent 401 on an
/// authenticated call (null if none was seen); [refreshStatus] /
/// [refreshDetail] are the refused refresh answer.
SessionEnd classifySessionEnd({
  String? lastAccessDenial,
  required int refreshStatus,
  String refreshDetail = '',
}) {
  if (refreshStatus == 403 && kRevokedRefreshDetails.contains(refreshDetail)) {
    return SessionEnd.revoked;
  }
  if (lastAccessDenial != null &&
      kRevokedAccessDetails.contains(lastAccessDenial)) {
    return SessionEnd.revoked;
  }
  return SessionEnd.expired;
}

/// What a quarantine holds about its owner (no PHI).
class QuarantineInfo {
  const QuarantineInfo({
    required this.userId,
    required this.organizationId,
    required this.at,
    required this.items,
    this.email = '',
  });

  factory QuarantineInfo.fromJson(Map<String, dynamic> json) => QuarantineInfo(
        userId: json['userId'] as String? ?? '',
        organizationId: json['organizationId'] as String? ?? '',
        email: json['email'] as String? ?? '',
        at: DateTime.tryParse(json['at'] as String? ?? '') ??
            DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
        items: json['items'] as int? ?? 0,
      );

  final String userId;
  final String organizationId;

  /// The owner's sign-in e-mail, to pre-fill the sign-in form (not PHI).
  final String email;
  final DateTime at;

  /// Number of unsynced items held (outbox ops + local-only drafts).
  final int items;

  bool ownedBy(String? userId, String? organizationId) =>
      userId != null &&
      userId == this.userId &&
      (this.organizationId.isEmpty ||
          organizationId == null ||
          organizationId.isEmpty ||
          organizationId == this.organizationId);

  Map<String, dynamic> toJson() => {
        'userId': userId,
        'organizationId': organizationId,
        'email': email,
        'at': at.toIso8601String(),
        'items': items,
      };
}

/// The sealed `quarantine` section of the encrypted store.
class Quarantine {
  Quarantine(this.store);

  static const String section = 'quarantine';

  final LocalStore store;

  QuarantineInfo? get info {
    final raw = store.doc[section];
    if (raw is! Map) return null;
    final owner = raw['owner'];
    return owner is Map
        ? QuarantineInfo.fromJson(owner.cast<String, dynamic>())
        : null;
  }

  bool get isActive => info != null;

  /// Seal [content] (section name → value) for [owner]. A second
  /// revocation of the same owner merges into the existing quarantine.
  Future<void> seal(QuarantineInfo owner, Map<String, Object?> content) async {
    final existing = store.doc[section];
    final merged = <String, Object?>{};
    if (existing is Map && existing['content'] is Map) {
      final prior = info;
      if (prior != null && prior.userId == owner.userId) {
        merged.addAll((existing['content'] as Map).cast<String, Object?>());
      }
    }
    content.forEach((k, v) {
      final prior = merged[k];
      if (prior is List && v is List) {
        merged[k] = [...prior, ...v];
      } else {
        merged[k] = v;
      }
    });
    await store.saveSection(section, {
      'owner': owner.toJson(),
      'content': merged,
    });
  }

  /// Hand the content back (the owner signed in again) and delete it.
  Future<Map<String, Object?>> release() async {
    final raw = store.doc[section];
    final content = raw is Map && raw['content'] is Map
        ? (raw['content'] as Map).cast<String, Object?>()
        : <String, Object?>{};
    await store.saveSection(section, null);
    return content;
  }

  /// Explicit, confirmed discard after an online sign-in.
  Future<void> discard() => store.saveSection(section, null);
}
