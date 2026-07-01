Alternative example using an acquisition-date source session folder.

Example:

    sourcedata/sub-0001/ses-20260523/meg/task-example/<original_file>.fif

With `sourcedata.sessions: "ignore"`, this folder organizes source files but the
BIDS target omits the session entity. Use `sourcedata.sessions: "include"` for
true multi-session BIDS datasets.
