allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
// flutter_reactive_ble 5.6.0 (reactive_ble_mobile) declares
// `compileSdkVersion 37`, a target name the SDK does not publish (API 37 ships
// as "android-37.0"). Compile it against the same SDK as the app (36); it
// uses no API-37-only call — the build fails loudly if that ever changes.
// minSdk / targetSdk and runtime behaviour are unaffected.
subprojects {
    val pinCompileSdk = {
        if (name == "reactive_ble_mobile") {
            (extensions.getByName("android") as groovy.lang.GroovyObject)
                .invokeMethod("compileSdkVersion", 36)
        }
    }
    if (state.executed) pinCompileSdk() else afterEvaluate { pinCompileSdk() }
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
