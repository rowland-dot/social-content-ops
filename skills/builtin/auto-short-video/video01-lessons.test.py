"""The video 01 lessons (issue 43) must be written into the skills Easel reads, and the lines they contradict gone.

Seam: the text the agent reads, the SKILL.md of each edited video skill. One marker phrase per lesson (S1 to S9 in
docs/research/2026-10-29-short-video-workflow-lessons-case-study-research.md, section 3), plus the old claims that are now wrong.
Run: .venv/bin/python -m pytest skills/builtin/auto-short-video/video01-lessons.test.py
CI runs it through tests/test_video01_lessons_in_skills.py, because pytest does not collect *.test.py by name.
"""
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1]


def skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


# ---- S1 and S2: auto-short-video ------------------------------------------------------------------

def test_s1_voice_is_fixed_first_and_subtitles_and_cuts_follow_its_real_pauses():
    text = skill("auto-short-video")
    assert "先定配音" in text
    assert "真实停顿" in text
    assert "静音检测" in text


def test_s1_the_tts_subtitle_timing_is_no_longer_taken_on_trust():
    # step 4 used to say only "use the SRT that comes with the TTS"
    text = skill("auto-short-video")
    step4 = text.split("4. **字幕", 1)[1].split("5. **BGM", 1)[0]
    assert "按字数估算" in step4  # the ChatGPT route's fallback, named, so the agent knows which line to re-time


def test_s1_music_goes_through_the_bgm_slot_now_that_the_assembler_lowers_it():
    # issue 45 made the slot lower the music under the voice, so issue 43's "mix it first, never use the slot" is gone
    text = skill("auto-short-video")
    step5 = text.split("5. **BGM", 1)[1].split("6. **合成成片", 1)[0]
    assert "audio_mix.py mix" not in step5
    assert "不要用 storyboard 的 `bgm` 字段" not in step5
    storyboard = text.split("storyboard 结构", 1)[1].split("```", 2)[1]
    assert '"bgm"' in storyboard  # the music is a storyboard field again


def test_s1_the_assembler_music_slot_is_described_as_it_now_behaves():
    text = skill("auto-short-video")
    assert "不会在说话时压低" not in text  # the issue 43 note about the old slot, true only before issue 45
    assert "还会循环播放" not in text
    assert "说完恢复" in text


def test_s1_video_cards_for_a_confirmed_vertical_video_are_rendered_at_1080x1920():
    text = skill("auto-short-video")
    assert "render_card.py" in text
    assert "--scale 1 --height 1920" in text
    assert "画幅确认硬门" in text  # the format-confirmation gate is kept


def test_s1_the_sound_check_tool_is_called_before_hand_over():
    # issue 49: step 7 used to say "measure it by hand with ffprobe, volumedetect, silencedetect"; it now calls the tool.
    # One copy of the line only (issue 43's S1 and issue 49 both touch it).
    text = skill("auto-short-video")
    assert "音频自检" in text
    assert "最后一句" in text.split("音频自检", 1)[1]
    step7 = text.split("7. **成片音频自检**", 1)[1].split("8. **交付**", 1)[0]
    assert "skills/shared/scripts/sound_check.py check" in step7
    assert "--storyboard" in step7 and "bgm_fade_out" in step7  # the allowed fade length comes from the storyboard
    assert "volumedetect" not in text  # the by-hand measuring line is gone
    assert text.count("sound_check.py") == 1


def test_the_sound_check_step_names_the_loudness_verdict():
    # issue 31: the check also judges the whole video's loudness against the owner's target
    step7 = skill("auto-short-video").split("7. **成片音频自检**", 1)[1].split("8. **交付**", 1)[0]
    assert "响度" in step7
    assert "-16 LUFS" in step7
    assert "-1 dBTP" in step7


def test_s2_replace_one_voice_line_method():
    text = skill("auto-short-video")
    assert "改一句配音" in text
    method = text.split("改一句配音", 1)[1]
    assert "15–20 毫秒" in method
    assert "重排" in method  # re-time every subtitle and cut after it


# ---- K4 (issue 44): the subtitle size comes from the storyboard, copied there from the brand's settings ------

def test_k4_storyboard_example_shows_subtitle_size_and_the_profile_section_says_to_copy_the_brand_size():
    text = skill("auto-short-video")
    example, profile_section = text.split("## Profile 感知", 1)
    assert "subtitle_size" in example
    assert "subtitle_size" in profile_section and "字幕规格" in profile_section


def test_k4_skill_says_the_command_line_wins_and_an_ass_file_cannot_take_a_size():
    text = skill("auto-short-video")
    assert "--sub-size` 优先" in text
    assert "现成的 `.ass`" in text and "改传 SRT" in text


# ---- S3: tts-voiceover, ChatGPT section -------------------------------------------------------------

def _chatgpt_section() -> str:
    return skill("tts-voiceover").split("## 走 ChatGPT 订阅", 1)[1].split("\n## 输入", 1)[0]


def test_s3_accent_note_says_record_important_lines_several_times_for_a_person_to_choose():
    section = _chatgpt_section()
    assert "口音" in section
    assert "单句多录" in section


def test_s3_line_timings_note_matches_what_the_route_does_now():
    # issue 47 landed first: the route measures each line's start from the pauses; only a line with no pause near it
    # keeps the character-count estimate (and prints a warning), so the note names that one case, not "all are estimates"
    section = _chatgpt_section()
    assert "分句时间" in section
    assert "没有找到停顿" in section


def test_s3_the_two_nobody_has_listened_claims_are_gone():
    text = skill("tts-voiceover")
    assert "没有人听过" not in text  # the owner listened on 2026-10-15; both the samples line and the last bullet said otherwise


# ---- S4: the LibTV wrapper (LibTV's own files under references/vendor stay untouched) ----------------

def test_s4_sound_is_off_on_every_clip():
    assert "enableSound=off" in skill("libtv-cli")


def test_s4_model_notes_are_dated_and_say_how_to_recheck_them():
    text = skill("libtv-cli")
    assert "2026-10-15" in text
    assert "libtv model search" in text
    for note in ("Seedance 2.5", "Kling 3.0 Turbo", "Kling 2.6"):
        assert note in text, note


def test_s4_one_clip_at_a_time_and_stop_at_the_first_out_of_compute_refusal():
    text = skill("libtv-cli")
    assert "一次只提交一段" in text
    assert "算力不足" in text


def test_s4_credits_are_not_shown_so_a_paid_ask_says_the_cost_cannot_be_seen():
    assert "命令行看不到费用" in skill("libtv-cli")


def test_s4_the_wrapper_no_longer_says_easel_adds_only_one_rule_and_keeps_the_install_rule():
    text = skill("libtv-cli")
    assert "只加一条自己的规则" not in text
    assert "ops/wsl-setup/setup.sh" in text


# ---- S5: "hands only" invites hands (ai-video-gen step 2, video-script scene guidance) ----------------

def test_s5_ai_video_gen_prompt_step_says_how_to_write_hands_and_elements_not_in_the_still():
    text = skill("ai-video-gen")
    prompt_step = text.split("2. **写好 prompt**", 1)[1].split("3. **文生视频**", 1)[0]
    assert "只拍手部" in prompt_step  # the phrase to avoid is named so it can be recognised
    assert "画面中不出现手" in prompt_step
    assert "不新增人物或手" in prompt_step


def test_s5_video_script_scene_guidance_says_the_same():
    text = skill("video-script")
    assert "只拍手部" in text
    assert "画面中不出现手" in text
    assert "不新增人物或手" in text


# ---- S9: video-script, the twist line and the plan file ----------------------------------------------

def test_s9_the_twist_line_stays_light_and_positive():
    text = skill("video-script")
    assert "反转" in text
    twist = text.split("反转", 1)[1][:200]
    assert "轻松积极" in twist
    assert "无聊" in twist  # the self-deprecating word the rule names


def test_s9_plan_file_keeps_the_current_state_first_and_the_change_log_last():
    text = skill("video-script")
    assert "当前状态" in text and "变更记录" in text
    assert text.index("当前状态") < text.index("变更记录")


# ---- S6: ai-music, Eleven Music through LibTV ---------------------------------------------------------

def test_s6_eleven_music_section_has_the_three_facts_and_points_at_the_libtv_skill():
    text = skill("ai-music")
    assert "Eleven Music" in text
    section = text.split("Eleven Music", 1)[1].split("\n## 规则", 1)[0]
    assert "只要纯音乐" in section  # no instrumental switch: the prompt must ask
    assert "1 秒" in section and "3–4 秒" in section  # about 1 s of silence first, its own 3-4 s fade at the end
    assert "至少长 5 秒" in section and "不要淡出收尾" in section  # the two ways round the fade
    assert "../libtv-cli/SKILL.md" in section  # ai-music's own script has no LibTV provider


# ---- S8: card-design ---------------------------------------------------------------------------------

def test_s8_space_between_notes_and_text_blocks():
    text = skill("card-design")
    assert "留间距" in text and "真空间" in text  # the rule stays; its measured pixel example moved to the account's guide (issue 125)


def test_s8_video_cards_keep_the_subtitle_band_clear_sized_from_the_brand_setting():
    text = skill("card-design")
    assert "字幕带" in text
    band = text.split("字幕带", 1)[1][:200]
    assert "字幕设置" in band


# ---- no single-brand rule written into a general skill (those live in each brand's own settings file) ----

CLIENT_ONLY = ("96 px", "96px", "0.175", "细笔刷", "粗笔刷", "评论问题", "Juniper")
EDITED = ("auto-short-video", "tts-voiceover", "libtv-cli", "ai-video-gen", "video-script", "ai-music", "card-design")


def test_no_brand_only_value_is_written_into_a_general_skill():
    for name in EDITED:
        text = skill(name)
        for value in CLIENT_ONLY:
            if name == "tts-voiceover" and value == "Juniper":
                continue  # Juniper is one of the nine ChatGPT voices in the voice table, not a casting rule
            assert value not in text, f"{name} carries the brand-only value {value}"
