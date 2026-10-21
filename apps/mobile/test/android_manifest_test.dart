/// Static guards for the Android release configuration (audit C3, H23,
/// D20). No Android SDK runs in CI, so these read the manifest and the
/// resource XML directly: a regression here would otherwise only show up
/// as a release APK that cannot reach the network, or PHI in a backup.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String read(String path) => File(path).readAsStringSync();

void main() {
  const main = 'android/app/src/main';

  test('release manifest declares INTERNET (C3)', () {
    expect(
      read('$main/AndroidManifest.xml'),
      contains('<uses-permission android:name="android.permission.INTERNET"/>'),
    );
  });

  test('backup is disabled and every domain is excluded (H23)', () {
    final manifest = read('$main/AndroidManifest.xml');
    expect(manifest, contains('android:allowBackup="false"'));
    expect(manifest, contains('android:fullBackupContent="@xml/backup_rules"'));
    expect(manifest,
        contains('android:dataExtractionRules="@xml/data_extraction_rules"'));

    final legacy = read('$main/res/xml/backup_rules.xml');
    final modern = read('$main/res/xml/data_extraction_rules.xml');
    for (final domain in ['root', 'file', 'database', 'sharedpref', 'external']) {
      expect(legacy, contains('<exclude domain="$domain" path="." />'));
      // once under <cloud-backup>, once under <device-transfer>
      expect(
        '<exclude domain="$domain" path="." />'.allMatches(modern).length,
        2,
      );
    }
    expect(modern, contains('<cloud-backup>'));
    expect(modern, contains('<device-transfer>'));
  });

  test('cleartext is refused in release, allowed only by the debug overlay',
      () {
    expect(
      read('$main/AndroidManifest.xml'),
      contains('android:networkSecurityConfig="@xml/network_security_config"'),
    );
    expect(read('$main/res/xml/network_security_config.xml'),
        contains('cleartextTrafficPermitted="false"'));
    expect(read('android/app/src/debug/res/xml/network_security_config.xml'),
        contains('cleartextTrafficPermitted="true"'));
    expect(
      File('android/app/src/profile/res/xml/network_security_config.xml')
          .existsSync(),
      isFalse,
      reason: 'profile builds are release-like: HTTPS only',
    );
  });
}
