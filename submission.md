models.py is responsible for defining SQLAlchemy models for all database entries:
- Association tables for user friendships, song tags, and playlist songs.
- Classes User, Tag, Song, ListeningEvent, Rating, Playlist, and Notification.


routes/songs.py - contains flask routes for finding and rating songs as well as recording listening events.

routes/users.py - contains flask routes for get_user, streaks, notifications, and read_notifications.

routes/feed.py - flask routes for activity, specifically listening_now is there too.

routes/playlists.py - flask routes for creating, editting and getting playlists.

services/feed_service.py - handles the logic for getting information on friends recent listening events.

services/notification_service.py - handles the logic related to creating/retrieving various notfications (like adding song to playlist or rating song.)

services/playlist_service.py - handles logic for creating and retrieving playlists.

services/search_service.py - handles logic for searching songs.

services/streak_service.py - handles logic related to listening streaks and events.

Data flow example - User listens to a song: POST     /songs/<song_id>/listen in routes/songs.py calls streak_service.record_listening_event(). This function creates a listening event and updates the users streak.

Pattern noticed: rate_song lives in notification_service.py rather than a 
dedicated ratings service which suggests rating a song's main effect is notifying the original sharer, and there's no separate Rating model either. 

Pattern noticed: no authorization checks anywhere (created_by in playlist creation, added_by when adding a song, user_id when logging a listen) in all cases the caller's identity is trusted from the request body with nothing verifying 
they actually are that user.




Issue #5 — The last song in a playlist never shows up

How you reproduced it — Ran pytest tests/test_playlists.py -v. The seed_playlist fixture creates a playlist with 5 songs at positions 1–5. test_playlist_returns_all_songs asserted len(songs) == 5 but got 4. That 5th song (highest position) was missing from the result.

How you found the root cause — Traced from the failing test → get_playlist_songs in playlist_service.py. The docstring says 'This function returns all songs in the playlist,' which contradicted the actual query. Reading the return statement line-by-line, songs[:-1] stood out as the one place count could be reduced by exactly one, matching the exact off-by-one in the test failure.

The root cause — There was a random slice at the end of get_playlist_songs: return [song.to_dict() for song in songs[:-1]]. The query returns songs correctly ordered by position, but the final line's songs[:-1] slice discards the last element of that already-correct list. 

Your fix and side-effect check: 
* The fix is just removing :-1 and leaving the code as:return [song.to_dict() for song in songs] 
* Re-ran test_playlist_returns_all_songs and test_playlist_returns_songs_in_order → both pass now. 
* Checked routes/playlists.py to confirm no other route relies on the old (buggy) truncated behavior



Issue #1 — My listening streak keeps resetting

How you reproduced it — Ran `pytest tests/test_streaks.py -v`. `test_streak_increments_on_sunday` seeds a streak of 1 on Saturday, then calls
`update_listening_streak` again on Sunday (one day later). Expected the streak to increment to 2 (consecutive day), but it reset to 1 instead. FAILED: assert 1 == 2.

How you found the root cause — Traced from the failing test → `update_listening_streak` in streak_service.py. The docstring states: "If the user listened yesterday: streak increments by 1" — with no exception mentioned for any particular day of the week. That contradicted what the code actually did, so I read the days_since_last == 1 branch line-by-line and found an extra condition (`today.weekday() != 6`) that isn't described anywhere in the docstring or streak rules.

The root cause — Python's date.weekday() returns 6 for Sunday (Monday=0 ... Sunday=6). The increment branch was written as `elif days_since_last == 1 and today.weekday() != 6:` which means it only increments the streak on a consecutive day if that day isn't a Sunday. When a user's consecutive listen happens to land on a Sunday, this condition is False, so execution falls through to the `else` branch and the streak resets to 1 instead of incrementing to 2 — even though exactly one day passed, which per the docstring should always increment.

Your fix and side-effect check:
Removed the `and today.weekday() != 6` clause, leaving `elif days_since_last == 1:` so any consecutive-day listen increments the streak regardless of which weekday it falls on. 
Re-ran `pytest tests/test_streaks.py -v` — all 5 tests passed, including test_streak_increments_on_sunday. 
Also checked test_streak_does_not_double_count_same_day and test_streak_resets_after_skipped_day to confirm the untouched branches (same-day no-op, multi-day reset) still behave correctly.