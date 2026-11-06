import json
import tempfile
from pathlib import Path

import streamlit as st

import merge_shapes
import svg_to_desmos

st.set_page_config(page_title="SVG / PNG / JPG to Desmos", page_icon="📐", layout="centered")
st.title("SVG / PNG / JPG to Desmos")
st.caption("將 SVG 向量圖或 PNG、JPG 圖片轉換成可匯入 Desmos 的數學表達式")
st.markdown(
    "SVG 會沿用原本的 FFT 曲線壓縮演算法；PNG、JPG 會先描圖成 SVG，"
    "再使用相同的轉換流程。照片及複雜漸層可能無法完美還原。"
)

with st.sidebar:
    st.header("轉換設定")
    scale = st.slider(
        "輸出解析度（數值越大通常越精細）",
        min_value=500, max_value=8000, value=2000, step=250
    )
    st.caption("較高解析度會增加運算時間與輸出大小。")
    trace_mode = st.selectbox(
        "PNG / JPG 描圖模式",
        ["彩色（適合插畫、Logo）", "黑白（適合線稿）"],
        help="彩色模式會保留主要色塊；黑白模式適合黑白線稿。"
    )
    st.caption("目前以填色圖形為主；不支援的 SVG 元素會被略過。")

uploaded = st.file_uploader("選擇檔案", type=["svg", "png", "jpg", "jpeg"])

if uploaded is not None:
    data = uploaded.getvalue()
    suffix = Path(uploaded.name).suffix.lower()
    is_svg = suffix == ".svg"
    st.write(f"檔案：**{uploaded.name}** · {len(data) / 1024:.1f} KB")

    if len(data) > 10 * 1024 * 1024:
        st.error("檔案太大，請上傳小於 10 MB 的檔案。")
    elif st.button("開始轉換", type="primary", use_container_width=True):
        try:
            with st.spinner("正在處理圖片並轉換成 Desmos 曲線，請稍候…"):
                with tempfile.TemporaryDirectory() as temp_dir:
                    input_path = Path(temp_dir) / uploaded.name
                    svg_path = Path(temp_dir) / "converted.svg"

                    if is_svg:
                        svg_path.write_bytes(data)
                    else:
                        # Load the native VTracer extension only when a raster image is converted.
                        # This keeps the web app startup independent from VTracer's native runtime.
                        import vtracer

                        image_format = "jpg" if suffix in [".jpg", ".jpeg"] else "png"
                        vector_svg = vtracer.convert_raw_image_to_svg(
                            data,
                            img_format=image_format,
                            colormode="binary" if trace_mode.startswith("黑白") else "color",
                            hierarchical="stacked",
                            mode="polygon",
                            filter_speckle=4,
                            color_precision=6,
                            layer_difference=16,
                            corner_threshold=60,
                            length_threshold=4.0,
                            max_iterations=10,
                            splice_threshold=45,
                            path_precision=3,
                        )
                        svg_path.write_text(vector_svg, encoding="utf-8")

                    # Raster traces need denser contour sampling to preserve corners
                    # and small details. Keep the original SVG sampling unchanged.
                    shapes = merge_shapes.load_svg_to_trig_splines(
                        str(svg_path), float(scale),
                        max_samples=512 if not is_svg else 256
                    )
                    if not shapes:
                        raise ValueError(
                            "沒有找到可轉換的填色圖形。請嘗試較簡單的圖片，"
                            "或確認 SVG 含有支援的 path、polygon、rect、circle 或 ellipse 元素。"
                        )

                    shapes = merge_shapes.collect_shapes_greedy(shapes)
                    shapes = merge_shapes.split_large_shapes(shapes)
                    common_expressions = merge_shapes.extract_common_latex(shapes)
                    expressions = svg_to_desmos.shapes_to_desmos(
                        shapes, common_expressions
                    )

                    txt_output = svg_to_desmos.expressions_to_txt(expressions)
                    expressions_json = json.dumps(
                        expressions, separators=(",", ":"), ensure_ascii=False
                    )
                    js_output = (
                        "var s=Calc.getState();\n"
                        "s['expressions']['list'] = "
                        + expressions_json
                        + ";\nCalc.setState(s);\n"
                    )

            st.session_state["svg_desmos_result"] = {
                "txt": txt_output,
                "js": js_output,
                "shape_count": len(shapes),
                "expression_count": len(expressions),
            }
        except Exception as exc:
            st.error(f"轉換失敗：{exc}")
            st.info(
                "請確認檔案格式正確且大小小於 10 MB。照片、漸層、細小雜訊及"
                "複雜背景可能產生大量曲線，建議先裁切主體或使用簡單圖案。"
            )

result = st.session_state.get("svg_desmos_result")
if result:
    st.success("轉換完成！")
    col1, col2 = st.columns(2)
    col1.metric("圖形群組", result["shape_count"])
    col2.metric("Desmos 表達式", result["expression_count"])

    st.subheader("下載結果")
    c1, c2 = st.columns(2)
    c1.download_button(
        "下載 desmos.js", data=result["js"], file_name="desmos.js",
        mime="text/javascript", use_container_width=True
    )
    c2.download_button(
        "下載 desmos.txt", data=result["txt"], file_name="desmos.txt",
        mime="text/plain", use_container_width=True
    )

    with st.expander("預覽 JavaScript"):
        st.code(result["js"], language="javascript")
    with st.expander("預覽文字表達式"):
        st.code(result["txt"], language="text")

    st.markdown(
        "[開啟 Desmos 計算機](https://www.desmos.com/calculator)，"
        "再將 **desmos.js** 的內容貼到瀏覽器開發者工具 Console 執行。"
    )

st.divider()
st.caption("SVG / PNG / JPG to Desmos · VTracer + FFT-based conversion")
