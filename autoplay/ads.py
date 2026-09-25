"""Telling whether a full-screen ad is covering the app.

An interstitial or a rewarded video is a normal activity belonging to the app's
own process - the ad SDK is a library, not a separate app - so the package name
says nothing. The *activity class* does: every mediation SDK puts its
full-screen ads in a handful of well-known classes, and those are what shows up
as the focused window while an ad is playing.

Detection is by window rather than by looking at the screen, because the two
questions have different answers. "Is an ad up?" is exact from `dumpsys`: the
device names the activity, with no threshold and no template. "Where is the
close button?" is not answerable that way at all - it appears only after a
countdown, moves around, and is drawn differently by every network - so that
half is left to the vision stack, which is what it is for.

The list below is matched as substrings against the focused `package/activity`,
case-insensitively. It covers the networks measured on the test device
(IronSource/LevelPlay, AppLovin, Vungle) plus the other common ones; an
unlisted network can be added by the testcase through `adPatterns=`.
"""

# Matched case-insensitively as substrings of "package/activity".
#
# These are class-name fragments, not whole names: AdMob alone ships
# `AdActivity`, `AppOpenAdActivity` and more, and the SDKs rename them between
# versions. A fragment survives that; a full class name does not.
AD_ACTIVITY_PATTERNS = (
    # Google AdMob / Google Mobile Ads
    "com.google.android.gms.ads.adactivity",
    "com.google.android.gms.ads.appopenadactivity",
    "com.google.android.gms.ads.outofcontext",
    # IronSource / LevelPlay - measured on the test device
    "com.ironsource.sdk.controller.controlleractivity",
    "com.ironsource.sdk.controller.interstitialactivity",
    "com.ironsource.mediationsdk",
    # AppLovin / MAX - measured on the test device
    "com.applovin.adview.applovininterstitialactivity",
    "com.applovin.adview.applovinfullscreen",
    "com.applovin.mediation.",
    "com.applovin.impl.adview",
    "com.applovin.sdk.applovinwebviewactivity",
    # Vungle / Liftoff - measured on the test device
    "com.vungle.warren.ui.vungleactivity",
    "com.vungle.ads.internal.ui.vungleactivity",
    # Unity Ads
    "com.unity3d.ads.adunit.adunitactivity",
    "com.unity3d.ads.adunit.adunitsoftwareactivity",
    "com.unity3d.services.ads.adunit",
    # Meta / Facebook Audience Network
    "com.facebook.ads.audiencenetworkactivity",
    "com.facebook.ads.interstitialadactivity",
    # Mintegral
    "com.mbridge.msdk.reward.player",
    "com.mbridge.msdk.interstitial",
    "com.mbridge.msdk.out",
    # Pangle / TikTok (ByteDance)
    "com.bytedance.sdk.openadsdk.activity",
    "com.bytedance.sdk.openadsdk.stub.activity",
    # Bigo Ads - measured on the test device: the interstitial after a song
    # plays and then ends on a CompanionAdActivity end card (app icon + "Xem
    # thêm"). Unlisted, isAdShowing() read it as the game and closeAd()
    # returned "no ad" while it sat on screen for good. The card has no close
    # control: its ">" disc is a click-through (it opened Play Store), and
    # only the back key dismisses it.
    "sg.bigo.ads.api",
    # Crackle - measured on the test device: the interstitial after the
    # tutorial song runs in the game's own process as
    # tech.crackle.core_sdk.ads.CrackleFullScreenActivity. Unlisted, it read
    # as the game and closeAd() reported "no ad" with the ad still up. Its
    # close is the white X disc in the top-left (`ad-close`).
    "tech.crackle.core_sdk.ads",
    # AdColony
    "com.adcolony.sdk.adcolonyinterstitialactivity",
    "com.adcolony.sdk.adcolonyadviewactivity",
    # Chartboost
    "com.chartboost.sdk.cbimpressionactivity",
    "com.chartboost.sdk.view.cbimpressionactivity",
    # Tapjoy
    "com.tapjoy.tjcofferwallactivity",
    "com.tapjoy.tjadunitactivity",
    # InMobi
    "com.inmobi.ads.rendering.inmobiadactivity",
    # Fyber / Digital Turbine
    "com.fyber.inneractive.sdk.activities",
    # Smaato, Verve, Digital Turbine generic
    "com.smaato.sdk.interstitial",
    # Generic fallbacks. Last, and deliberately narrow: a bare "ad" would match
    # "com.amanotes.beathopper" and every activity with "load" or "thread" in
    # the name. These require the word to stand on its own in a class name.
    "interstitialactivity",
    "rewardedactivity",
    "rewardedvideoactivity",
    "fullscreenadactivity",
)


def looks_like_ad(activity, patterns=AD_ACTIVITY_PATTERNS):
    """True when this `package/activity` is a known full-screen ad container."""
    if not activity:
        return False
    needle = activity.lower()
    return any(p in needle for p in patterns)


def matched_pattern(activity, patterns=AD_ACTIVITY_PATTERNS):
    """Which pattern identified this activity, for the log line."""
    if not activity:
        return ""
    needle = activity.lower()
    for pattern in patterns:
        if pattern in needle:
            return pattern
    return ""


def activity_class(activity):
    """The class part of "package/activity", shortened for a log line.

    `com.amanotes.beathopper/com.ironsource.sdk.controller.ControllerActivity`
    reads as `ControllerActivity` - the part that says which SDK is showing,
    without the package repeated twice.
    """
    if not activity:
        return ""
    tail = activity.split("/")[-1]
    return tail.rsplit(".", 1)[-1] or tail
