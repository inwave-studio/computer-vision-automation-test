# UI element database: element id -> the image(s) that identify it.
#
# Paths are relative to this file. An element that looks the same everywhere is
# a single path. An element drawn several ways - the same close button as a bare
# x on one popup and a circled x on another - lists every variant, and find()
# matches whichever one is actually on screen (design.md task 7).
db = {
    "splash-screen": "DB/Screens/splash.png",
    "welcome-screen": "DB/welcome-th.png",
    "paywall": "DB/Screens/screen-sub.png",
    "genre-btn": "DB/genre-button.png",
    "play-button": "DB/play-button.png",
    "close-popup": "DB/close-popup.png",
    # Ad close controls, tried by closeAd() before it falls back to reading
    # text. Network end-cards label nothing - the Pangle rewarded card is an
    # icon-only X on a dark disc, so OCR has nothing to find and the text
    # fallback polls for the full 90s without ever tapping. The crop is the
    # disc only, cut away from the video behind it, which changes every ad.
    # Second variant: the Crackle interstitial (CrackleFullScreenActivity) puts
    # a black X on a white disc in the top-left, the inverse of the Pangle one,
    # and scores nothing against it. Cut at stream size (48px), disc only.
    "ad-close": [
        "DB/Ads/close-x-dark.png",
        "DB/Ads/close-x-light.png",
    ],
    # The Pangle rewarded card that shows an app install (TTRewardExpressVideo
    # Activity) offers no X at all, only a ">>" skip disc in the top-right -
    # and no text, so closeAd() polled the whole 90s without a tap and the
    # test aborted. closeAd() already tries an `ad-skip` id; this is it. Cut
    # at stream size, the disc only. Scores 1.0 on that card; the best
    # non-ad hit measured is 0.77 on a Play Store page, which closeAd() never
    # searches - it only looks while an ad activity holds focus.
    "ad-skip": "DB/Ads/skip-dark.png",
    "song-card": [
        "DB/songcard-play.png",
        "DB/songcard-ad.png",
    ],
    # A song row is identified by its badge, not by the whole card: the card is
    # mostly cover art and a title, so a full-card template only ever matches
    # the one song it was cut from. The badge on the left is on every row, and
    # the hexagon on the right is what says whether the song costs an ad.
    "song-badge": "DB/Home/song-badge-play.png",
    "song-ad-lock": "DB/Home/song-hex-ad.png",
    # The other state of that right-hand hexagon: yellow with a white play
    # arrow, on songs that need no ad. Cut at stream size from the hexagon's
    # face only (60px), away from the cover art beside it. Home and the result
    # screen draw the same card. Use threshold=0.8: real hexagons score
    # 0.95-1.0, the best miss measured is 0.73 on cover art.
    "song-play": "DB/Home/song-hex-play.png",
    "settings-close": "DB/Home/settings-close.png",
    # The X on the event popup Home opens with ("JP TRACK COMING", a framed
    # card over the song list). None of the other close templates reach the
    # 0.88 it takes to trust them here: measured on that popup, ad-close 0.87,
    # panel-close 0.84, settings-close 0.79, close-popup 0.56. It matters more
    # than it looks - the popup leaves the HUD and the Setting button in plain
    # view above it, so "star-hud and settings-button are there" read as Home
    # and the song list was then counted through the popup (2 songs, HUD
    # digits unreadable). Cut at stream size, 46px. Needs
    # find("event-close", threshold=0.9): the X glyph is shared with the
    # Setting close, which this scores 0.65 on - 1.0 / 0.99 on the popup.
    "event-close": "DB/Home/event-close.png",
    # The X that closes a panel opened FROM inside Setting (the language
    # chooser, the game-settings sheet). A different control from
    # `settings-close`: tapping that one closes the Setting screen behind the
    # panel and leaves the panel itself on top, covering the rows a test still
    # has to reach. Grey hexagon, centred at the foot of the panel. Needs
    # find("panel-close", threshold=0.88): the two X hexagons are the same
    # glyph in different greys, so at the 0.75 default this also matches the
    # Setting close at 0.79 and a test would "close the panel" by closing the
    # screen behind it. Measured - real panel X 0.99, Setting X 0.79.
    "panel-close": "DB/Home/panel-close.png",
    # The other way a Setting sub-panel closes: GAME SETTINGS has no X at all,
    # only a pink "Đồng ý" button. Without this, closing that panel found
    # nothing, and the Setting rows kept showing dimmed through the overlay -
    # OCR still read them, so the next row "was found" and the tap landed on
    # the overlay instead. A template, not findText("Đồng ý"): text needles
    # are what once tapped "Indonesia" for "done" in the language list. Cut at
    # stream size (544 wide) from the button's pink face.
    "panel-ok": "DB/Home/panel-ok.png",
    # Shop Ball. Both are cut from a frame at the size autoplay actually
    # streams (max_size=1200 -> 544x1200 here), NOT from a native 1080-wide
    # screenshot, and both are >=40px on their short side. That floor is not
    # cosmetic: MIN_TEMPLATE_PX in vision.py floors the scale sweep at
    # 40/shortest_side, so a 16x25 glyph can only ever be searched at 2.5x and
    # up and never matches at all. The earlier 64px native crops hit the same
    # wall from the other side - they need scale 0.50 on a 544 frame but their
    # floor is 0.625, so they were forced off their peak and scored 0.75
    # (ball-equipped) and 0.82 (ball-lock), under the thresholds asked for
    # here. Re-cut at stream size they score 0.999 and 0.998.
    #
    # `ball-lock` is the padlock alone, trimmed of the tile behind it: that
    # background is ball art and differs per tile, so a crop that includes it
    # only matches the one tile it came from. Needs
    # find("ball-lock", threshold=0.85) - measured on the ball grid, 0.85
    # keeps 7 real locks and finds nothing on a Home screen holding no locks,
    # while 0.9 drops to 5.
    "ball-lock": "DB/Home/ball-lock.png",
    "ball-equipped": "DB/Home/ball-equipped.png",
    # The Home entry in the bottom tab bar, used to get back to Home from
    # another tab. A separate element from `home-tab`, which is the English
    # "HOME" label cropped while the tab was SELECTED - a bright magenta raised
    # card. That card, not the house icon, is what it matches, so on a
    # Vietnamese device sitting on the Ball tab it scores 0.99 on whichever tab
    # is currently selected and "go home" taps re-select the tab you are
    # already on. This one is the house icon over "TRANG CHỦ" in its
    # unselected state, cut at stream size like the three tabs beside it.
    # Two variants because the tab is drawn two ways and they do not match each
    # other: unselected it is a dim house on the bar, selected it is a bright
    # magenta raised card. Measured - the unselected crop scores 0.96 from
    # another tab and 0.00 on Home, so one variant alone only ever finds the
    # tab in one of the two states a test can be in.
    "tab-home": [
        "DB/Home/tab-home.png",     # unselected: what you see from another tab
        "DB/Home/tab-home-on.png",  # selected: already on Home
    ],
    "home-tab": "DB/Home/btn-tab-home.png",
    "settings-button": "DB/Home/setting.png",
    # Home HUD (Smoke/test_home.py). The star and gem entries are the icons
    # only, deliberately cropped away from their numbers: the counters change
    # every session, so a template that included the digits would stop matching
    # the moment the balance did. The number is read separately with readText.
    "profile-button": "DB/Home/profile-button.png",
    "star-hud": "DB/Home/star-icon.png",
    "gem-hud": "DB/Home/gem-icon.png",
    "vip-button": "DB/Home/vip-button.png",
    "vip-mission": "DB/Home/vip-mission.png",  # no longer tested (dropped from test_home.py)
    "tab-shop": "DB/Home/tab-shop.png",
    "tab-ball": "DB/Home/tab-ball.png",
    "tab-discover": "DB/Home/tab-discover.png",
    "tile-normal": "DB/Gameplay/tile-normal.png",
    "arrow": "DB/Gameplay/arrow_v2.png",
    "btnAutoplayClose": "DB/Gameplay/btnAutoplayClose.png",
    "white-ball": "DB/Gameplay/white-ball.png",
    "bounceOnTiles": "DB/Gameplay/bounceOnTiles.png",
}
