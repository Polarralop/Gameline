"""py2app build for Gameline.app. Use ./build_app.sh rather than calling this directly.

    ./build_app.sh          full build: a standalone dist/Gameline.app (for the demo)
    ./build_app.sh --alias  alias build: the .app runs this source folder, so code
                            changes show up on the next restart without rebuilding
"""

from setuptools import setup

APP = ["packaging/launcher.py"]
DATA_FILES = [
    # Compiled app icon (see packaging/make_icon.py): macOS 26 reads Assets.car,
    # older versions fall back to AppIcon.icns.
    ("", ["packaging/icon-build/Assets.car"]),
    # Prebuilt demo "game" (packaging/build_demo_game.sh), so users don't need Xcode tools.
    ("demo", ["packaging/icon-build/GamelineDemoGame"]),
    ("assets/icons", [
    "assets/icons/calendar.svg", "assets/icons/chart.svg", "assets/icons/demo.svg", "assets/icons/gear.svg",
    "assets/icons/logo.svg", "assets/icons/logo-ok.svg", "assets/icons/logo-risk.svg",
]),
]
OPTIONS = {
    "iconfile": "packaging/icon-build/AppIcon.icns",
    "packages": ["gameline", "anthropic", "desktop_notifier", "pypdf", "psutil", "dotenv",
                 # google-genai's own dependencies. The `google` namespace package itself
                 # (genai, auth) can't be traced by py2app; build_app.sh copies it in.
                 "requests", "tenacity", "websockets", "distro", "cryptography", "pyasn1", "pyasn1_modules"],
    "includes": ["rubicon.objc"],
    "plist": {
        "CFBundleName": "Gameline",
        "CFBundleDisplayName": "Gameline",
        "CFBundleIdentifier": "ca.polarralop.gameline",
        "CFBundleIconName": "AppIcon",  # the icon inside Assets.car
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
        # Lets the notification permission prompt name the app.
        "NSUserNotificationAlertStyle": "banner",
    },
}

setup(
    name="Gameline",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
