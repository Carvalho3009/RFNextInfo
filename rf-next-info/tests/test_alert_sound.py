import tempfile
import unittest
import wave
from pathlib import Path

from app.alert_sound import (
    install_alert_sound,
    resolve_alert_sound,
    validate_alert_sound,
)


class AlertSoundTest(unittest.TestCase):
    @staticmethod
    def _wave(path: Path, seconds: int = 1) -> None:
        with wave.open(str(path), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(8_000)
            target.writeframes(b"\0\0" * 8_000 * seconds)

    def test_installs_validated_wave_under_content_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "alerta.wav"
            target = root / "managed"
            self._wave(source)
            metadata = validate_alert_sound(source)
            filename = install_alert_sound(source, target)
            resolved = resolve_alert_sound(target, filename)

        self.assertEqual(metadata["duration_seconds"], 1.0)
        self.assertEqual(len(filename), 68)
        self.assertIsNotNone(resolved)

    def test_rejects_invalid_or_long_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "alerta.wav"
            invalid.write_bytes(b"not a wav")
            with self.assertRaisesRegex(ValueError, "validado"):
                validate_alert_sound(invalid)
            long = root / "longo.wav"
            self._wave(long, seconds=11)
            with self.assertRaisesRegex(ValueError, "10 segundos"):
                validate_alert_sound(long)


if __name__ == "__main__":
    unittest.main()
