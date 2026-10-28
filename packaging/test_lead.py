"""Musical timing/safety cases for the opt-in lead rhythm mode."""
import dataclasses
import os
from pathlib import Path
import random
import sys
import tempfile
import weakref
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import numpy as np
    import lead
    import stepgen as sg
except ImportError:
    sg = None


def analysis(attacks=(0.5, 1.25, 2.0, 4.0, 4.75, 6.0, 8.0, 8.75, 10.0, 12.0), follow=1):
    n = int(16 * sg.SR / sg.HOP) + 1
    beat = np.zeros(n)
    melody = np.zeros(n)
    for t in np.arange(0, 16, 0.5):
        beat[round(t * sg.SR / sg.HOP)] = 1
    for t in attacks:
        melody[round((t + 0.016) * sg.SR / sg.HOP)] = 1
    return sg.Analysis(16, 120, 0, beat, beat, np.ones(n), np.ones(n), melody, np.ones(n),
                       np.ones((64, n)), 0, 16, 2, np.ones((8, 2)) / np.sqrt(2), np.ones(8), np.zeros(8),
                       step_env=beat, beat_env=beat, melody_env=melody, melody_cent=np.ones(n),
                       vocals=np.zeros(8), follow=np.full(8, float(follow)), stems=True,
                       melody_source='lead', lead_attacks=np.array(attacks))


@unittest.skipIf(sg is None, 'Audio checks run after installing build dependencies')
class LeadTests(unittest.TestCase):
    def spec(self, **kw):
        sp = sg.load_patterns()[2]
        return dataclasses.replace(sp, **({'hold_rate': 0, 'jump': 0, 'target_meter': 0,
                                           'melody_follow': 1, 'density': 2, 'max_nps': 6} | kw))

    def test_source_follow_and_override(self):
        a = analysis()
        sections = [{'label': 'intro', 'letter': 'A', 'vocals': 0, 'start': 0, 'end': 8}]
        self.assertTrue(np.all(sg.follow_for(a, sections, self.spec()) == 1))
        a.melody_source = 'singing'
        self.assertLess(sg.follow_for(a, sections, self.spec())[0], 0.4)
        self.assertTrue(np.all(sg.follow_for(a, sections, self.spec(), {'all': 1}) == 1))
        a.melody_source = 'lead'
        self.assertTrue(np.all(sg.follow_for(a, sections, self.spec(), {'intro': 0.25}) == 0.25))

    def test_drum_only_and_silence_have_no_lead_steps(self):
        a = analysis(())
        self.assertEqual(sg.make_chart(a, self.spec(), [], random.Random(1)), [])

    def test_high_follow_remains_supported_after_all_passes(self):
        a = analysis()
        spec = self.spec(rhythm_lock=1, rhythm_repeat=1, run_breaks=1, recovery=1)
        notes = sg.make_chart(a, spec, [(4, 0, 4)], random.Random(9))
        self.assertGreater(len(notes), 0)
        self.assertTrue(all(lead.supported(a, n.row) for n in notes))
        self.assertEqual(lead.alignment(a, notes), 1)
        self.assertTrue(all(n.panels for n in notes))
        self.assertGreaterEqual(min(y.row - x.row for x, y in zip(notes, notes[1:])), round(spec.min_gap * 4))
        trace = notes.melody_trace
        self.assertEqual(trace['stages'][-1]['stage'], 'footwork safety')
        self.assertTrue(set(trace['stages'][-1]['retained_phrase_rows']) <= set(trace['selected_phrase_rows']))

    def test_low_follow_keeps_beat_component(self):
        a = analysis(follow=0.2)
        notes = sg.make_chart(a, self.spec(), [], random.Random(1))
        self.assertTrue(any(not lead.supported(a, n.row) for n in notes))

    def test_peak_detection_does_not_fill_sustain(self):
        env = np.zeros(1000)
        env[100:500] = 1
        self.assertEqual(len(lead.attack_times(env, sg.SR, sg.HOP)), 1)
        self.assertEqual(len(lead.attack_times(np.zeros(1000), sg.SR, sg.HOP)), 0)

    def test_final_score_values_alignment(self):
        a = analysis()
        good = [sg.Note(4, 0.5, 1, 0)]
        bad = [sg.Note(6, 0.75, 1, 0)]
        self.assertGreater(lead.selection_score(a, good, 60), lead.selection_score(a, bad, 70))
        a.melody_source = 'singing'
        self.assertEqual(lead.selection_score(a, good, 60), 60)

    def test_spectral_cache_rejects_another_analysis(self):
        a, other = analysis(), analysis()
        other.mel = np.zeros_like(other.mel)
        sg._MEL_STATS[id(a)] = (weakref.ref(other), np.full(64, 999), np.ones(64))
        sg._similar(a, 1, 2)
        self.assertIs(sg._MEL_STATS[id(a)][0](), a)
        self.assertTrue(np.all(sg._MEL_STATS[id(a)][1] == 1))

    def test_short_pairs_fit_notes_per_second_limit(self):
        pair = [sg.Note(0, 0, 1, 0)]
        self.assertTrue(lead.fits(sg.Note(2, 0.21, 1, 0), pair, 2, 3.6))
        full = [sg.Note(i * 2, i * 0.21, 1, 0) for i in range(4)]
        self.assertFalse(lead.fits(sg.Note(8, 0.84, 1, 0), full, 2, 3.6))

    def test_missing_stems_fails_before_writing(self):
        with self.assertRaisesRegex(ValueError, 'stems'):
            sg.generate(Path('missing.wav'), Path('must-not-exist'), melody_source='lead')

    def test_empty_lead_can_write_a_complete_chart_and_stats(self):
        import soundfile as sf
        from layout import song_dirs, file_name
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, BEATSMITH_DATA=str(Path(tmp) / 'data')):
            src, out = Path(tmp) / 'drums.wav', Path(tmp) / 'out'
            sf.write(src, np.zeros(sg.SR), sg.SR)
            data, _ = song_dirs(out, file_name('Drums', ''))
            stems = data / '.stems'
            stems.mkdir(parents=True)
            for part in ('vocals', 'other', 'drums', 'bass'):
                (stems / f'{part}.ogg').touch()
            with patch.object(sg, 'analyze', return_value=analysis(())), patch.object(sg, 'song_onsets', return_value=None):
                sm = sg.generate(src, out, title='Drums', specs=[self.spec()], stems=True,
                                 keep_format=True, art=False, melody_source='lead')
            self.assertTrue(sm.is_file())
            self.assertTrue((data / 'Drums.stats.md').is_file())
            self.assertIn('"melody_source": "lead"', (data / 'Drums.stepgen.json').read_text())

    def test_easier_chart_stays_subset_and_safe(self):
        a = analysis()
        top = sg.make_chart(a, self.spec(), [], random.Random(1))
        easier = sg.back_off(a, top, dataclasses.replace(self.spec(), name='Easy', min_gap=1, density=0.5), random.Random(1))
        self.assertTrue({n.row for n in easier} <= {n.row for n in top})
        self.assertTrue(all(lead.supported(a, n.row) for n in easier))

    def test_separated_piano_attacks_sustains_and_silence(self):
        import soundfile as sf
        starts = np.array([0.5, 1.25, 3.0, 4.5, 6.0])
        y = np.zeros(8 * sg.SR, dtype=np.float32)
        for i, t in enumerate(starts):
            length = 1.5 if i == 2 else 0.45
            ts = np.arange(int(length * sg.SR)) / sg.SR
            # A struck harmonic tone, with a long third note. No generated assets
            # are committed; all samples live in a temporary directory.
            envelope = np.minimum(1, ts / 0.005) * np.exp(-ts / (length / 2))
            wave = sum(np.sin(2 * np.pi * (330 + i * 55) * h * ts) / h for h in (1, 2, 3))
            part = 0.2 * envelope * wave
            pos = round(t * sg.SR)
            y[pos:pos + len(part)] += part
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            sf.write(folder / 'other.ogg', y, sg.SR)
            sf.write(folder / 'vocals.ogg', np.zeros_like(y), sg.SR)
            env, _, _ = sg._stem_melody(folder, int(len(y) / sg.HOP) + 1, 'lead')
            found = lead.attack_times(env, sg.SR, sg.HOP)
            self.assertTrue(all(np.min(abs(found - t)) <= 0.075 for t in starts), found)
            self.assertLessEqual(sum(np.min(abs(starts - t)) > 0.075 for t in found), 1, found)
            sf.write(folder / 'other.ogg', np.zeros_like(y), sg.SR)
            empty, _, _ = sg._stem_melody(folder, len(env), 'lead')
            self.assertEqual(len(lead.attack_times(empty, sg.SR, sg.HOP)), 0)


if __name__ == '__main__':
    unittest.main()
