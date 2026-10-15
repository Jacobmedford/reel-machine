# Shooting for reel-machine

How to film so the kit gives you its best cut, and why you never grade by hand.

## The short version
1. 4K, 30 fps, **HDR off**, vertical.
2. Lock exposure and focus on your face before you roll.
3. **Clip the mic to your collar.** Don't hold it in front of your face.
4. Light your face, not the room.
5. Say each line until it lands, then keep going. Leave a breath between lines.
6. Drop the raw takes into the chat. Don't trim them first.
7. Never color grade. Your style pack does it.

## Camera settings (set once)
- **4K at 30 fps.** The kit runs at 30 fps end to end. Not 24, not 60. (iPhone: Settings > Camera > Record Video.)
- **Auto frame rate off** (iPhone: Auto FPS). With it on, the phone drops the frame rate in a dim room, which makes
  motion stutter and lip sync harder to check. Turn it off and add light instead.
- **HDR video off.** HDR takes come out grey or blown out on most screens. If one gets through, the kit converts it
  to standard range and tells you so, but a standard-range shoot looks better.
- **No log profiles** (Apple Log and the like). Log footage needs a grade on every clip, the opposite of the goal.
- Tap and hold on your face until exposure and focus lock. Exposure that shifts between takes makes every cut show.
- Optional upgrade: a manual camera app (Blackmagic Camera is free) that locks white balance, shutter (1/60) and
  ISO, so every take in a session matches exactly. Worth it for hi-fi days.

## The mic: the one change that matters most
A mic held in front of your chin costs three things:
- **The lip sync check.** QA matches your mouth frame by frame. A hand over the chin weakens it.
- **Type behind your head.** The cutout traces you, and a hand and mic in front of the face make a messy edge.
- **The caption band.** Captions sit at chest height, right where your hand would be.

Clip the transmitter to your collar or shirt neckline, about a hand's width below your chin. Same sound, clean frame.

## Lo-fi days (selfie, daily posts)
- Phone at arm's length or on a small stand at eye level. The back camera if a stand lets you; the front one is
  fine handheld.
- Eyes about a third of the way down the frame. Leave room above your head: that's where the hook and the words
  behind your head go.
- Keep your hands below your chest when you gesture, so they stay out of the caption band.
- Exports from Edits or CapCut are already cut in the pauses. Send the raw take instead.

## Hi-fi days (sit-down, produced)
- Shoot **vertical 4K** on a tripod, locked off. The kit makes a wide and a close framing (about 1.6x) from one
  camera, and only vertical 4K has the pixels for a sharp close. Horizontal 4K cropped to vertical leaves it soft.
- Frame waist up with headroom. Sit 1 to 2 m in front of the background.
- A camera that also streams over USB usually streams at 720p. Record 4K in the camera, to its card, instead.
- Keep the same set from video to video. A familiar frame is part of the look.

## Light
- One soft light at about 45 degrees to the side and a little above your eyes: a window or a softbox.
- Your face a touch brighter than the wall behind you. That separation makes the cutout clean.
- Avoid ceiling light alone. It puts your eyes in shadow, more so under a cap.
- A black shirt against a dark background confuses the cutout. Pick a shirt that stands off your wall.

## How to talk to it
- Repeat a line until it lands. The kit keeps the **last** clean take of each line, so restart as often as you want.
- Leave about one second of silence before the first line and after the last.
- Say names and terms clearly. Anything it mishears, tell the agent once and it goes on the project's fix list.

## When it asks for screen recordings
The storyboard lists exactly what it needs (for example "p06: 8 to 10 s of the dashboard updating"). Record at full
resolution with the cursor visible and send it back. Real screens beat anything generated.

## Why you don't grade
- The kit applies one grade to the whole video at render, from your style pack (the `grade` value in its
  `style.json`). Every video matches every other one.
- A good shoot (locked exposure, soft light, HDR off) gets you most of the look. Grading by hand adds a round trip
  and a re-encode per clip, which is the time this kit is meant to save.
- If the grade feels off, say so. The agent changes it once in your pack and it carries to every video after.

## When a real grade is worth it
A hero piece that deserves a hand grade: grade the raw take in your editor, export Rec.709 at a high bitrate, set
`"grade": "none"` in that project's `style/style.json`, then make the video from the graded file.
