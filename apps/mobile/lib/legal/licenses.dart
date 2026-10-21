// Open-source licence notices (M8.1 L2).
//
// Flutter's build collects every Dart package's LICENSE into NOTICES, which
// showLicensePage lists. Two components shipped in the APK are NOT in that
// file and are registered here:
// * Google ML Kit barcode scanning — native Android library pulled in by
//   mobile_scanner; proprietary, free, governed by the ML Kit terms;
// * the Material Icons font bundled by `uses-material-design: true`, which
//   Flutter distributes under CC BY 4.0 (attribution required).
// See LICENSES.md for the full bill of materials.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

const String appDisplayName = 'Aditya BioNova Smart HMS';

const String mlKitNotice =
    'This app uses Google ML Kit barcode scanning '
    '(com.google.mlkit:barcode-scanning 17.3.0, through the mobile_scanner '
    'plugin) to read QR codes and medicine barcodes. Scanning runs on the '
    'device; no image is sent to Google by this app.\n\n'
    'ML Kit is provided by Google LLC under the ML Kit Terms of Service '
    '(https://developers.google.com/ml-kit/terms) and the Google APIs Terms '
    'of Service (https://developers.google.com/terms). It is not open-source '
    'software.';

const String materialIconsNotice =
    'Material Icons font (MaterialIcons-Regular.otf) © Google LLC.\n\n'
    'Licensed under the Creative Commons Attribution 4.0 International '
    'License (CC BY 4.0): https://creativecommons.org/licenses/by/4.0/\n\n'
    'Distributed unmodified with the Flutter SDK.';

/// Native Android libraries linked by flutter_reactive_ble (M8.2). Flutter's
/// NOTICES lists only Dart packages, so these are registered here.
const List<(String, String)> nativeBleLibraries = [
  ('RxAndroidBle 1.16.0 (com.polidea.rxandroidble2)', 'Apache License 2.0'),
  ('RxJava 2 / RxKotlin 2.4.0 / RxAndroid 2.1.1 (io.reactivex.rxjava2)',
      'Apache License 2.0'),
  ('Protocol Buffers Java Lite 3.25.3 (com.google.protobuf)',
      'BSD 3-Clause License, Copyright 2008 Google Inc.'),
  ('Kotlin standard library (org.jetbrains.kotlin)', 'Apache License 2.0'),
];

const String apache2Notice =
    'Licensed under the Apache License, Version 2.0 (the "License"); you may '
    'not use this file except in compliance with the License. You may obtain '
    'a copy of the License at https://www.apache.org/licenses/LICENSE-2.0\n\n'
    'Unless required by applicable law or agreed to in writing, software '
    'distributed under the License is distributed on an "AS IS" BASIS, '
    'WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.';

bool _registered = false;

/// Adds the notices Flutter does not collect itself. Idempotent.
void registerAdditionalLicenses() {
  if (_registered) return;
  _registered = true;
  LicenseRegistry.addLicense(() async* {
    yield const LicenseEntryWithLineBreaks(
        <String>['Google ML Kit (barcode scanning)'], mlKitNotice);
    yield const LicenseEntryWithLineBreaks(
        <String>['Material Icons font'], materialIconsNotice);
    for (final (name, licence) in nativeBleLibraries) {
      yield LicenseEntryWithLineBreaks(<String>[name],
          licence.startsWith('Apache') ? '$licence\n\n$apache2Notice' : licence);
    }
  });
}

void openLicences(BuildContext context, {String? version}) {
  registerAdditionalLicenses();
  showLicensePage(
    context: context,
    applicationName: appDisplayName,
    applicationVersion: version,
    applicationLegalese: '© Aditya BioNova. Proprietary software.\n'
        'The open-source and third-party components listed here remain '
        'under their own licences.',
  );
}
