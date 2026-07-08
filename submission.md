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

How you found the root cause — Traced from the failing test → get_playlist_songs in playlist_service.py. The docstring says 'This function returns all songs in the playlist,' which contradicted the actualy query. Reading the return statement line-by-line, songs[:-1] stood out as the one place count could be reduced by exactly one, matching the exact off-by-one in the test failure.

The root cause — There was a random slice at the end of get_playlist_songs: return [song.to_dict() for song in songs[:-1]]. The query returns songs correctly ordered by position, but the final line's songs[:-1] slice discards the last element of that already-correct list. 

Your fix and side-effect check: 
* The fix is just removing :-1 and leaving the code as:return [song.to_dict() for song in songs] 
* Re-ran test_playlist_returns_all_songs and test_playlist_returns_songs_in_order → both pass now. 
* Checked routes/playlists.py to confirm no other route relies on the old (buggy) truncated behavior