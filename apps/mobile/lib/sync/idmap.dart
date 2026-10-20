/// Local → server id mapping.
///
/// Offline-first rule: a mutation captured with no network has no server id
/// yet (a patient registered in airplane mode, for example). The device
/// generates the id itself and records the op's `localRef`; every other
/// queued mutation refers to it as `$ref:<localRef>` (see [IdMap.placeholder]).
///
/// The sync engine substitutes references right before pushing, in queue
/// order. A reference that is still unresolved (its creating op has not
/// been accepted yet) DEFERS the dependent op to the next run instead of
/// pushing a bogus id — the server FKs would reject it, and worse, it could
/// attach a queue entry to the wrong patient.
library;

class IdMap {
  IdMap([Map<String, String>? ids]) : _ids = Map<String, String>.of(ids ?? const {});

  static const String prefix = r'$ref:';

  final Map<String, String> _ids;

  /// The placeholder a queued payload stores for a not-yet-synced entity.
  static String placeholder(String localRef) => '$prefix$localRef';

  bool isPlaceholder(Object? value) =>
      value is String && value.startsWith(prefix);

  String? serverIdOf(String localRef) => _ids[localRef];

  void put(String localRef, String serverId) {
    _ids[localRef] = serverId;
  }

  void clear() => _ids.clear();

  Map<String, dynamic> toJson() => {'ids': _ids};

  factory IdMap.fromJson(Map<String, dynamic> json) {
    final raw = json['ids'];
    return IdMap(raw is Map<String, dynamic> ? raw.cast<String, String>() : null);
  }

  /// Deep-copy [payload] with every `$ref:…` replaced by its server id.
  ///
  /// Returns `null` when at least one reference is still unresolved — the
  /// caller must NOT push this payload yet.
  Map<String, dynamic>? substitute(Map<String, dynamic> payload) {
    var unresolved = false;

    Object? walk(Object? value) {
      if (value is String && value.startsWith(prefix)) {
        final server = _ids[value.substring(prefix.length)];
        if (server == null) {
          unresolved = true;
          return value;
        }
        return server;
      }
      if (value is Map) {
        return value.map((k, v) => MapEntry(k.toString(), walk(v)));
      }
      if (value is List) return value.map(walk).toList();
      return value;
    }

    final resolved = walk(payload);
    if (unresolved) return null;
    return resolved is Map<String, dynamic> ? resolved : null;
  }

  /// True when [payload] still contains an unresolved local reference.
  static bool hasUnresolved(Map<String, dynamic> payload, IdMap ids) =>
      ids.substitute(payload) == null;

  static final RegExp _pathRef = RegExp(r'\$ref:([^/?#]+)');

  /// Every local ref mentioned in [value]: a JSON payload (deep) or a path
  /// such as `/encounters/$ref:abc/vitals`.
  static Set<String> refsIn(Object? value) {
    final out = <String>{};
    void walk(Object? v) {
      if (v is String) {
        if (v.startsWith(prefix)) {
          out.add(v.substring(prefix.length));
        } else if (v.contains(prefix)) {
          for (final m in _pathRef.allMatches(v)) {
            out.add(m.group(1)!);
          }
        }
      } else if (v is Map) {
        v.values.forEach(walk);
      } else if (v is List) {
        v.forEach(walk);
      }
    }

    walk(value);
    return out;
  }

  /// [path] with `$ref:<local>` segments replaced by server ids; null when
  /// one is still unresolved.
  String? substitutePath(String path) {
    if (!path.contains(prefix)) return path;
    var unresolved = false;
    final out = path.replaceAllMapped(_pathRef, (m) {
      final server = _ids[m.group(1)!];
      if (server == null) {
        unresolved = true;
        return m.group(0)!;
      }
      return server;
    });
    return unresolved ? null : out;
  }

  int get length => _ids.length;
}
