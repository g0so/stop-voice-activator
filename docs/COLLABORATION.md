# Working together through Git

## Publish this handoff once

Upload **the contents of github-ready/** as the repository root, not the entire original Voice workspace. Include the hidden .gitignore. The folder is self-contained and includes personal recordings for your collaboration. No upload, remote creation, commit or push has been performed by this handoff.

If publishing with Git locally, first copy github-ready's contents to a separate folder outside the existing /home/a/SIH checkout, then initialize/connect that new folder to your chosen GitHub repository. This avoids accidentally adding other projects from the parent repository. The original Voice folder currently belongs to a Git repository rooted at /home/a/SIH.

Both collaborators then clone the same GitHub repository. All following commands run inside that clone. Replace placeholders with real names; no repository URL has been assumed.

## Friend → hardware owner

1. Friend starts a branch for one experiment. Claude Code reads CLAUDE.md/AGENTS.md first; friend explicitly authorizes any training or build.
2. Friend commits source changes and a new versioned model/sketch only after documenting validation. Preserve V10-R1. Do not send only a .tflite file: Arduino needs the complete sketch folder and C model header.
3. Every candidate commit should include:
   - complete `outputs/live_stop_<version>/` folder, all frontend files, model header and reference test vectors;
   - `.tflite`, SHA256, threshold, preprocessing details and software versions;
   - validation/test results, compilation status, known limitations;
   - exact `.ino` path and a short test plan.
4. Friend pushes their branch and gives the owner the **branch name and commit hash**. Merge via a pull request if preferred. Large public datasets/caches stay ignored.

The owner updates without overwriting local work:

```bash
git status
git fetch origin
git switch <shared-branch>
git pull --ff-only
git rev-parse HEAD
```

If Git reports local changes or a conflict, preserve them and resolve it together; do not use reset --hard or force-push as a shortcut. Commit or stash deliberate local edits before switching branches.

## Test on the owner's PC / ESP32

1. Open the exact `.ino` from the candidate commit in Arduino IDE. Keep every accompanying file in its folder. A desktop WAV replay alone does not test the microphone/device.
2. Board: **ESP32 Dev Module**, ESP32 package **3.3.11**. Select the actual serial port (historically /dev/ttyUSB0).
3. Upload when ready. Open Serial Monitor at **115200**, reset with EN, and save the whole startup log.
4. If model self-test prints ERROR, stop speech testing and return the log. Do not raise tolerance or change the threshold locally.
5. After PASS/READY, stay quiet for ten seconds. Say STOP ten times with three-second gaps. Then say START, SHORT, STARK, STOT and SHOP five times each, also separated by three seconds. Record detections per word and any extra triggers. Follow any additional candidate-specific plan from the friend.
6. Note distance, fan/noise, speaking style, inference time and the reported memory/work values. This short test is diagnostic, not a statistically strong false-activations-per-hour result.

## Hardware owner → friend

Copy hardware-tests/TEMPLATE.md to a uniquely named report, e.g. hardware-tests/2026-09-30-v14.md. Put the full serial log in a matching .txt file. Record the **model commit hash before making the report commit**, plus the .tflite SHA256 if supplied.

```bash
git add hardware-tests/<report>.md hardware-tests/<serial-log>.txt
git commit -m "Report ESP32 test for <model version>"
git push
```

Use your shared branch or a separate results branch/PR as agreed. The friend pulls these commits and fixes the next version. Avoid simultaneous edits to the same report/model files. Never overwrite an old report with a different model's results.

## Baseline / rollback

V10-R1 remains under outputs/live_stop_reviewed_v10/. To compare or return to it, open and upload that complete sketch. No destructive Git rollback is needed. V13 has no deployable model yet: do not try to upload best.keras.
