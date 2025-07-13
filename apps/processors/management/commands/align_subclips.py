from django.core.management.base import BaseCommand
from apps.processors.models import Clips, Subclip
import json


class Command(BaseCommand):
    help = "Align start_time and end_time for Clips and Subclips using word-level timing"

    def handle(self, *args, **options):
        from pathlib import Path

        total_clips = 0
        total_subclips = 0

        for clip in Clips.objects.filter(video__id=329):
            video = clip.video
            if not video or not video.srt_file:
                continue

            try:
                with video.srt_file.open("r") as f:
                    srt_data = json.load(f)
            except Exception as e:
                self.stderr.write(f"[ERROR] Failed to load SRT: {e}")
                continue

            words = []
            for fragment in srt_data.get("fragments", []):
                fragment_text = " ".join(fragment.get("lines", [])).strip()
                fragment_words = fragment_text.split()
                if not fragment_words:
                    continue
                start = float(fragment["begin"])
                end = float(fragment["end"])
                duration = end - start
                word_duration = duration / len(fragment_words)
                for i, word in enumerate(fragment_words):
                    word_start = start + i * word_duration
                    word_end = word_start + word_duration
                    words.append({
                        "word": word.strip(),
                        "start": word_start,
                        "end": word_end
                    })

            def align_text_to_times(text):
                text_words = text.strip().split()
                best_start = None
                best_end = None
                best_score = -1

                for i in range(len(words) - len(text_words) + 1):
                    match = True
                    for j in range(len(text_words)):
                        if words[i + j]["word"].strip(".,?!").lower() != text_words[j].strip(".,?!").lower():
                            match = False
                            break
                    if match:
                        score = len(text_words)
                        if score > best_score:
                            best_start = words[i]["start"]
                            best_end = words[i + len(text_words) - 1]["end"]
                            best_score = score

                return best_start, best_end

            # Align clip
            clip_start, clip_end = align_text_to_times(clip.text or "")
            if clip_start is not None and clip_end is not None:
                clip.start_time = clip_start
                clip.end_time = clip_end
                clip.save()
                total_clips += 1
            else:
                self.stderr.write(f"[CLIP] Failed to align: {clip.text}")

            # Align subclips
            for subclip in clip.subclip_set.all():
                sub_start, sub_end = align_text_to_times(subclip.text or "")
                if sub_start is not None and sub_end is not None:
                    subclip.start_time = sub_start
                    subclip.end_time = sub_end
                    subclip.save()
                    total_subclips += 1
                else:
                    self.stderr.write(f"[SUBCLIP] Failed to align: {subclip.text}")

        self.stdout.write(f"✅ Aligned {total_clips} Clips and {total_subclips} Subclips")
