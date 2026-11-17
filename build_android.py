import argparse
import os
from pathlib import Path
import subprocess
import sys

from flet_android_background.android import configure_android_project
from flet_cli.commands.build import Command
import yaml


class AndroidBuild(Command):
    def register_flutter_extensions(self):
        super().register_flutter_extensions()
        slider = self.flutter_packages_dir / "flet_circular_slider"
        source = slider / "lib/src/flet_circular_slider.dart"
        text = source.read_text(encoding="utf-8")
        old = "package:flutter/material.dart"
        new = "package:material_ui/material_ui.dart"
        if old not in text and new not in text:
            raise RuntimeError("Circular slider imports changed; review compatibility")
        source.write_text(text.replace(old, new), encoding="utf-8")
        pubspec = slider / "pubspec.yaml"
        data = yaml.safe_load(pubspec.read_text(encoding="utf-8"))
        data["dependencies"]["material_ui"] = "^1.6.0"
        pubspec.write_text(yaml.safe_dump(data), encoding="utf-8")

    def run_flutter(self):
        subprocess.run([
            sys.executable, "-m", "flet_android_notifications.patcher",
            "--project-root", str(self.flutter_dir),
        ], check=True)
        configure_android_project(self.flutter_dir, service_type="dataSync")
        super().run_flutter()


def main():
    os.chdir(Path(__file__).resolve().parent)
    parser = argparse.ArgumentParser()
    command = AndroidBuild(parser)
    options = parser.parse_args(["apk", "--yes", "--log-format", "plain", *sys.argv[1:]])
    command.handle(options)


if __name__ == "__main__":
    main()
