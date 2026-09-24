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
    "song-card": [
        "DB/songcard-play.png",
        "DB/songcard-ad.png",
    ],
    "home-tab": "DB/Home/btn-tab-home.png",
    "settings-button": "DB/Home/setting.png",
    "tile-normal": "DB/Gameplay/tile-normal.png",
    "arrow": "DB/Gameplay/arrow_v2.png",
    "btnAutoplayClose": "DB/Gameplay/btnAutoplayClose.png",
    "white-ball": "DB/Gameplay/white-ball.png",
    "bounceOnTiles": "DB/Gameplay/bounceOnTiles.png",
}
