// M8.1 L2: open-source licence notices are reachable in the app and include
// the two components Flutter's NOTICES file does not cover.
import 'package:aditya_bionova_mobile/legal/licenses.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'rural_mode_test.dart' show bootGraph, pumpHome;

void main() {
  test('ML Kit and Material Icons notices are registered once', () async {
    registerAdditionalLicenses();
    registerAdditionalLicenses();
    final entries = await LicenseRegistry.licenses.toList();
    final packages = entries.expand((e) => e.packages).toList();
    expect(packages.where((p) => p == 'Google ML Kit (barcode scanning)'),
        hasLength(1));
    expect(packages.where((p) => p == 'Material Icons font'), hasLength(1));
    final text = entries
        .expand((e) => e.paragraphs)
        .map((p) => p.text)
        .join('\n');
    expect(text, contains('developers.google.com/ml-kit/terms'));
    expect(text, contains('not open-source'));
    expect(text, contains('creativecommons.org/licenses/by/4.0'));
  });

  testWidgets('settings menu opens the licence page', (tester) async {
    final graph = await bootGraph();
    await pumpHome(tester, graph);
    await tester.tap(find.byKey(const Key('settings-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('menu-licences')));
    await tester.pumpAndSettle();
    expect(find.byType(LicensePage), findsOneWidget);
    expect(find.text(appDisplayName), findsWidgets);
  });
}
