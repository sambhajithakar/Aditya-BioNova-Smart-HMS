/// Network awareness without polling.
///
/// The app learns whether the API is reachable from the requests it makes
/// anyway: [ReachabilityTransport] wraps the real transport and reports
/// every answer (any HTTP status → the server is reachable) and every
/// network-level exception (→ offline) to a [NetworkMonitor]. There is no
/// background ping loop — that would cost battery on low-end phones. The
/// scheduler's backoff retry doubles as the gentle "are we back?" probe,
/// and app resume / manual sync probe too.
///
/// Network **type** (metered mobile data vs Wi-Fi) is a hook: a platform
/// adapter (e.g. `connectivity_plus`, not bundled to keep the native
/// footprint small) can call [NetworkMonitor.setMetered]. When metered, the
/// scheduler defers *large* ops only (see [SyncPolicy]); small clinical
/// drafts still go out immediately.
library;

import 'package:flutter/foundation.dart';

import '../api/transport.dart';

enum Reachability { unknown, online, offline }

class NetworkState {
  const NetworkState({this.reachability = Reachability.unknown, this.metered = false});

  final Reachability reachability;

  /// True on metered (mobile-data) connections when a platform adapter
  /// reported it; false when unknown.
  final bool metered;

  bool get isOffline => reachability == Reachability.offline;

  bool get isOnline => reachability == Reachability.online;

  NetworkState copyWith({Reachability? reachability, bool? metered}) =>
      NetworkState(
        reachability: reachability ?? this.reachability,
        metered: metered ?? this.metered,
      );

  @override
  bool operator ==(Object other) =>
      other is NetworkState &&
      other.reachability == reachability &&
      other.metered == metered;

  @override
  int get hashCode => Object.hash(reachability, metered);
}

class NetworkMonitor extends ValueNotifier<NetworkState> {
  NetworkMonitor([super.value = const NetworkState()]);

  /// Fired once each time the device goes from offline to online — the
  /// scheduler syncs then ("sync on connectivity regain").
  VoidCallback? onRegained;

  void reportReachable() {
    final was = value.reachability;
    if (was == Reachability.online) return;
    value = value.copyWith(reachability: Reachability.online);
    if (was == Reachability.offline) onRegained?.call();
  }

  void reportUnreachable() {
    if (value.reachability == Reachability.offline) return;
    value = value.copyWith(reachability: Reachability.offline);
  }

  /// Platform hook: metered (mobile data) or not.
  void setMetered(bool metered) {
    if (value.metered == metered) return;
    value = value.copyWith(metered: metered);
  }
}

/// Transport decorator that feeds a [NetworkMonitor].
class ReachabilityTransport implements ApiTransport {
  ReachabilityTransport(this.inner, this.monitor);

  final ApiTransport inner;
  final NetworkMonitor monitor;

  @override
  Future<ApiResponse> send({
    required String method,
    required String path,
    Map<String, dynamic>? body,
    Map<String, String>? headers,
  }) async {
    try {
      final res = await inner.send(
          method: method, path: path, body: body, headers: headers);
      // 502/503/504 come from a proxy: the device has a network but the
      // API is not answering — still "online" for the radio, the op
      // itself backs off.
      monitor.reportReachable();
      return res;
    } catch (_) {
      monitor.reportUnreachable();
      rethrow;
    }
  }
}

/// What a sync run may send on the current network.
class SyncPolicy {
  const SyncPolicy({
    this.pauseLargeOnMetered = true,
    this.largePayloadBytes = 16 * 1024,
  });

  /// Defer ops whose JSON body exceeds [largePayloadBytes] while metered.
  final bool pauseLargeOnMetered;
  final int largePayloadBytes;

  /// True when [payloadBytes] should wait for an unmetered network.
  bool defer(int payloadBytes, NetworkState network) =>
      pauseLargeOnMetered &&
      network.metered &&
      payloadBytes > largePayloadBytes;
}
