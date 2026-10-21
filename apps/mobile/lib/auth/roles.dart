/// Role interfaces: which home tabs a role sees.
///
/// The server is the authority — `/auth/me` reports `role` (owner, admin,
/// doctor, nurse, receptionist, pharmacist, lab_technician, billing,
/// auditor, support) and `permissions`. The app maps the role to one of
/// four interfaces and, when the server reports permissions, additionally
/// hides any tab whose write permission the user lacks. Hiding a tab is a
/// convenience only: every action is still authorised by the API.
///
/// | Interface      | Roles                                   | Tabs (in order)                                  |
/// |----------------|-----------------------------------------|--------------------------------------------------|
/// | doctor         | doctor                                  | Queue · Consult · Rx · Patients · Sync           |
/// | reception      | receptionist, nurse, billing, others    | Queue · Register · Appointments · Billing · Sync |
/// | administrator  | owner, admin                            | Overview · Queue · Register · (Rx) · Billing · Sync |
/// | pharmacy       | pharmacist                              | Stock · Patients · Sync                          |
/// | Rural Clinic   | any (device setting)                    | Register · Queue · Fast Rx · Bill (+ Sync in bar) |
library;

enum RoleInterface { doctor, reception, administrator, pharmacy }

RoleInterface roleInterfaceOf(String? role) => switch (role) {
      'doctor' => RoleInterface.doctor,
      'owner' || 'admin' => RoleInterface.administrator,
      'pharmacist' => RoleInterface.pharmacy,
      _ => RoleInterface.reception,
    };

/// Permission each tab needs when the server reports permissions.
abstract final class TabPermissions {
  static const queue = {'queue.read', 'queue.manage'};
  static const register = {'patient.write'};
  static const patients = {'patient.read'};
  static const appointments = {'appointment.write', 'appointment.read'};
  static const consult = {'encounter.write'};
  static const rx = {'prescription.sign'};
  static const billing = {'billing.invoice'};
  static const overview = {'report.read'};
  static const stock = {'inventory.read', 'inventory.manage'};
}

/// The permission set reported by `/auth/me`, or null when the server did
/// not report one (then only the role decides).
class Permissions {
  const Permissions(this.keys);

  static const Permissions unknown = Permissions(null);

  factory Permissions.fromJson(Map<String, dynamic> body) {
    final raw = body['permissions'];
    if (raw is! List) return unknown;
    final keys = raw.whereType<String>().toSet();
    // An empty list from an old server stub means "not reported".
    return keys.isEmpty ? unknown : Permissions(keys);
  }

  final Set<String>? keys;

  /// True when any of [needed] is granted (or nothing was reported).
  bool any(Set<String> needed) =>
      keys == null || needed.any(keys!.contains);
}
