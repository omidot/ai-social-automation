"""Biểu đồ dựng TỪ CHÍNH LỜI NÓI.

Đo trên bản nháp thật: mô hình viết kịch bản chỉ gắn 1 thẻ 'chart' trên 38
card, nên 95% thời lượng màn hình trống trong khi giọng đọc đang đọc ra đầy
số liệu. autoviz.mjs đọc bản ghi lời nói (có mốc thời gian từng từ) và dựng
biểu đồ đúng giây con số được nói ra.

Ràng buộc quan trọng nhất: KHÔNG BỊA. Mọi nhãn/số phải cắt từ lời nói, và
những con số KHÔNG phải số liệu (mảnh tên model, ngày tháng, số phiên bản)
phải bị loại -- lỗi đó từng sinh ra 3 biểu đồ rác trên một bản thu.
"""
import json
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "video"

pytestmark = pytest.mark.needs_node


def _charts(words):
    """Chạy chartsFromSpeech trên một chuỗi từ, trả về danh sách biểu đồ."""
    script = (
        "import('./tools/autoviz.mjs').then(m => {"
        f"  const w = {json.dumps(words, ensure_ascii=False)};"
        "   console.log(JSON.stringify(m.chartsFromSpeech(w)));"
        "});"
    )
    r = subprocess.run(["node", "-e", script], cwd=VIDEO,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


def _say(text, t0=0.0, step=0.4):
    """Biến một câu thành chuỗi từ có mốc thời gian, như Whisper trả về."""
    out = []
    t = t0
    for w in text.split():
        out.append({"w": w, "start": round(t, 2), "end": round(t + step, 2)})
        t += step
    return out


def test_extracts_a_comparison_chart_from_spoken_numbers():
    """Câu thật trong một bản thu: ba mức hạn ngạch đọc liền nhau. Đây đúng
    là thứ bản tham chiếu vẽ thành biểu đồ, còn ta thì để khung đen."""
    words = (_say("Gói Plus chỉ được từ 5 đến 45 tin.", 0)
             + _say("Gói Pro 100 đô được 25 đến 225 tin.", 4)
             + _say("Gói Pro 200 đô nhận 100 đến 900 tin.", 8))
    charts = _charts(words)
    assert len(charts) == 1
    c = charts[0]
    assert c["kind"] == "hbar" and c["unit"] == "tin"
    assert [(i["label"], i["value"]) for i in c["items"]] == [
        ("Gói Plus", 45), ("Gói Pro 100 đô", 225), ("Gói Pro 200 đô", 900)]


def test_chart_is_timed_to_when_the_number_is_spoken():
    """Hình phải bật lên đúng lúc con số được nói, không phải đầu câu."""
    words = (_say("Gói Plus chỉ được từ 5 đến 45 tin.", 10)
             + _say("Gói Pro 200 đô nhận 100 đến 900 tin.", 20))
    c = _charts(words)[0]
    # "45" là từ thứ 8 của câu đầu (t=10 + 7*0.4)
    assert 12.5 <= c["start"] <= 13.5


def test_model_name_digits_never_become_data():
    """'GPT6' bị tách thành số 6 đã dựng ra biểu đồ rác trên bản thu thật.
    Chỉ token số nguyên chất mới được coi là số."""
    words = _say("GPT6 Astra vừa thay thế GPT-5 hoàn toàn.", 0)
    assert _charts(words) == []


def test_dates_are_not_charted():
    """'ngày 3 tháng 9' là mốc lịch, không phải số liệu để vẽ cột."""
    words = _say("OpenAI bắt đầu tung ra Astra từ ngày 3 tháng 9.", 0)
    assert _charts(words) == []


def test_numbers_without_a_unit_are_ignored():
    """Con số không đơn vị thì không biết nó đo cái gì -- vẽ ra là số trôi nổi."""
    words = _say("Họ nói con số đó là 272 và không giải thích gì thêm.", 0)
    assert _charts(words) == []


def test_the_number_carrying_the_unit_wins_not_the_biggest():
    """'Gói Pro 100 đô được 25 đến 225 tin' -- 100 là mô tả gói, 225 tin mới
    là điều đang được nói tới."""
    words = _say("Gói Pro 100 đô được 25 đến 225 tin.", 0)
    c = _charts(words)[0]
    assert c["items"][0]["value"] == 225
    assert c["items"][0]["label"] == "Gói Pro 100 đô"


def test_separate_contexts_are_not_merged_into_one_chart():
    """Bản thu thật đọc hạn ngạch 'mỗi năm giờ' rồi chuyển sang 'hàng tuần'.
    Gộp hai nhóm vào một biểu đồ là dựng ra số liệu SAI dù mọi con số đều
    có thật -- một câu không số chen vào giữa là dấu hiệu đổi ngữ cảnh."""
    words = (_say("Gói Plus chỉ được từ 5 đến 45 tin.", 0)
             + _say("Với hạn mức hàng tuần còn siết chặt hơn nhiều.", 4)
             + _say("Gói Pro 200 đô nhận 100 đến 900 tin.", 9))
    charts = _charts(words)
    assert len(charts) == 2, "hai ngữ cảnh phải là hai biểu đồ riêng"
    assert all(len(c["items"]) == 1 for c in charts)


def test_conditional_openers_are_rejected_as_labels():
    """'Nếu bạn không biết = 15' là nhãn rác, không phải số liệu."""
    words = _say("Nếu bạn không biết thì mất khoảng 15 phút.", 0)
    assert _charts(words) == []


def test_a_chart_never_carries_more_rows_than_fit_the_frame():
    words = []
    for i in range(8):
        words += _say(f"Gói số {i} được {10 + i} tin.", i * 3)
    for c in _charts(words):
        assert len(c["items"]) <= 4


def test_panel_title_comes_from_the_spoken_lead_in_sentence():
    """Bản tham chiếu luôn có một nhãn ngắn phía trên khối số ("Giá đầu ra
    mỗi 1 triệu token"). Lấy nó từ CÂU DẪN có thật ngay trước nhóm số liệu
    -- đúng cách người đọc đã nói, nên không phải bịa ra."""
    words = (_say("Bảng hạn ngạch tin mỗi năm giờ.", 0)
             + _say("Gói Plus chỉ được 45 tin.", 3)
             + _say("Gói Pro nhận 225 tin.", 6))
    c = _charts(words)[0]
    assert c["title"] == "Bảng hạn ngạch tin mỗi năm giờ"


def test_panel_title_is_empty_when_the_lead_in_carries_its_own_number():
    """Câu có số là một mốc dữ liệu khác, không phải lời dẫn -- lấy nó làm
    tiêu đề sẽ in nhầm một số liệu thành nhãn."""
    words = (_say("Trước đó chỉ có 10 tin.", 0)
             + _say("Gói Plus chỉ được 45 tin.", 3)
             + _say("Gói Pro nhận 225 tin.", 6))
    assert all(c.get("title", "") == "" for c in _charts(words))


def test_align_mjs_wires_autoviz_in():
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "chartsFromSpeech" in src
    assert "autoCharts" in src
    # chỉ chạy khi có mốc thời gian THẬT -- đoán theo khoảng lặng thì con số
    # sẽ rơi sai chỗ, hình bật lên lúc không ai nói tới nó
    assert "if (usedRealWords)" in src
