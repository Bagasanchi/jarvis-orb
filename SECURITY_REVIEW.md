# Local review — 2026-11-16

Scope: the six assistant upgrades, source credential scan, regression tests and
manual review of action approval, microphone input, project launching, history
and screenshot routing. These changes have not been pushed to GitHub.

## Results

- detect-secrets 1.5.0 scanned 47 source/documentation/workflow files: zero
  potential secrets after the existing exact documentation/fixture exceptions.
- Synthetic tests cover delayed speaker echo, room reflection and double-talk.
- Conversation panel rendered, prefilled a correction and queued typed input.
- Windows declined notification-icon creation in this execution session; the
  implementation falls back to normal minimize/close behavior. Actual taskbar
  behavior remains unverified in the user's desktop session.
- Live microphone opening still fails with PortAudioError, so room AEC and real
  voice recognition remain unverified on the laptop.
- No new application dependencies were added. A current dependency vulnerability
  audit and Bandit rerun could not be performed locally: PyPI tooling installation
  was unavailable. The prior GitHub security run does not validate this new code.

## Findings fixed with the user's approval

1. **Pending approvals survive cancellation of a reply.** The reply-stream cancel
   event is not supplied to the confirmation broker. In a mocked reproduction,
   cancelling the turn and subsequently approving its dialog still invoked the
   pending deletion. Approval is still required; cancellation alone does not
   invalidate the request. Recommendation: bind approvals to a turn cancellation
   token and reject any action after cancellation, including late dialogs.
   **Fixed:** requests carry their turn cancellation token; approval is checked
   again before deletion, capture and upload. Cancelled queued requests are
   discarded, and late approval is rejected.
2. **Forget everything leaves the visible transcript.** The action clears SQLite
   items and AI prompt history, but not the new in-memory conversation panel.
   The old conversation can remain visible until quitting. Recommendation: clear
   display history and any outstanding reply updates in the same confirmed action.
   **Fixed:** confirmed clearing now resets display and AI history, pending orb
   text and correction input. Turn IDs are never reused; old callbacks and AI
   history commits/restores cannot repopulate a cleared conversation.

These findings were reproduced with mock data; no user memories were deleted
and no real screenshot was captured or uploaded. Regression coverage includes
late approval, cancellation during screen encoding, denied deletion, stale
stream callbacks and interrupted deletion replies. A screenshot upload already
started before cancellation cannot be recalled; a deletion already committed
cannot be undone.
