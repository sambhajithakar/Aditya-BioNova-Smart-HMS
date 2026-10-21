import java.util.Base64
import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// ---------------------------------------------------------------------------
// Release signing (M4: "signed release build process — keys never committed")
//
// The keystore and its passwords live ONLY in android/key.properties and the
// .keystore/.jks file itself; android/.gitignore excludes key.properties,
// **/*.keystore and **/*.jks, so no key material can enter the repository.
//
// Without that file a RELEASE build fails (M8.1), so a debug-signed APK can
// never be mistaken for a distributable one. Demo and CI builds opt in to
// the Android debug key explicitly:
//   HMS_ALLOW_DEBUG_SIGNING=1 flutter build apk --release
// (or the Gradle property -Phms.allowDebugSigning=true). Debug builds and
// `flutter run` are unaffected.
//
// One-time setup on the release machine:
//   keytool -genkeypair -v -keystore ~/keys/aditya-bionova-release.jks \
//       -keyalg RSA -keysize 2048 -validity 10000 -alias bionova
// then create android/key.properties:
//   storeFile=/absolute/path/aditya-bionova-release.jks
//   storePassword=…
//   keyAlias=bionova
//   keyPassword=…
// ---------------------------------------------------------------------------
val keystorePropertiesFile = rootProject.file("key.properties")
val allowDebugSigning = System.getenv("HMS_ALLOW_DEBUG_SIGNING") == "1" ||
    (project.findProperty("hms.allowDebugSigning") as String?) == "true"

// LAN demo build (docs/DEMO.md): `--dart-define=HMS_DEMO_LAN=true`. Flutter
// hands dart-defines to Gradle as base64 in the "dart-defines" property, so
// the one flag drives both the app (lib/demo/demo_server.dart) and the
// cleartext network policy overlay in src/demoLan/res. Never release-signed.
val demoLan = ((project.findProperty("dart-defines") as String?) ?: "")
    .split(",")
    .filter { it.isNotBlank() }
    .map { String(Base64.getDecoder().decode(it)) }
    .contains("HMS_DEMO_LAN=true")
val keystoreProperties = Properties().apply {
    if (keystorePropertiesFile.exists()) {
        keystorePropertiesFile.inputStream().use { load(it) }
    }
}

android {
    namespace = "com.adityabionova.smarthms"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.adityabionova.smarthms"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://flutter.dev/to/review-gradle-config)
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (keystorePropertiesFile.exists()) {
            create("release") {
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
            }
        }
    }

    if (demoLan) {
        sourceSets.getByName("release").res.srcDir("src/demoLan/res")
    }

    buildTypes {
        release {
            signingConfig = when {
                keystorePropertiesFile.exists() -> signingConfigs.getByName("release")
                // explicit opt-in only: local testing and demos, never distribution
                allowDebugSigning -> signingConfigs.getByName("debug")
                else -> null
            }
        }
    }
}

// Fail before anything is built when a release variant is requested without
// the owner's key and without the explicit debug-signing opt-in.
gradle.taskGraph.whenReady {
    val releaseRequested = allTasks.any {
        it.project == project && it.name.startsWith("assemble") && it.name.endsWith("Release") ||
            it.project == project && it.name.startsWith("bundle") && it.name.endsWith("Release")
    }
    if (releaseRequested && demoLan && keystorePropertiesFile.exists()) {
        throw GradleException(
            "HMS_DEMO_LAN builds allow cleartext HTTP and must never carry the release key: " +
                "move android/key.properties aside and use HMS_ALLOW_DEBUG_SIGNING=1.")
    }
    if (releaseRequested && !keystorePropertiesFile.exists() && !allowDebugSigning) {
        throw GradleException(
            "Release signing key missing: create android/key.properties " +
                "(docs/ANDROID_BUILD.md §3), or set HMS_ALLOW_DEBUG_SIGNING=1 to build " +
                "a debug-signed APK for local testing only (never distribute it).")
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
