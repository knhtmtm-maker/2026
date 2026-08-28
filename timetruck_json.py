# aaaaaaaaaaa
#bbbbbbbbbbbbb

import cv2
import numpy as np
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import time
import json  # JSON操作用モジュールを追加

# --- 高速化・検出のための設定 ---
SCALE = 0.3  # 処理時の縮小率（0.5 = 縦横半分、面積1/4で処理）

# バウンディングボックスの大きさの上限値（元の動画の解像度ベースでピクセル数を指定）
MAX_BOX_WIDTH = 300   # 幅の上限値
MAX_BOX_HEIGHT = 300  # 高さの上限値

# 選択可能なカラープール（色追加・調整もここから可能です）
ALL_COLOR_POOL = {
    "Red":     {"box_color": (0, 0, 255),   "margins": (10, 70, 80, 0.15)},
    "Blue":    {"box_color": (255, 0, 0),   "margins": (10, 70, 80, 0.15)},
    "Green":   {"box_color": (0, 255, 0),   "margins": (10, 70, 80, 0.15)},
    "Yellow":  {"box_color": (0, 255, 255), "margins": (10, 70, 80, 0.15)},
    "Pink":    {"box_color": (147, 20, 255),"margins": (10, 70, 80, 0.15)},
    "Purple":  {"box_color": (128, 0, 128), "margins": (10, 70, 80, 0.15)},
    "Orange":  {"box_color": (0, 165, 255), "margins": (10, 70, 80, 0.15)},
    "Cyan":    {"box_color": (255, 255, 0), "margins": (10, 70, 80, 0.15)}
}

detected_colors_data = {}

# 複数点サンプリングと履歴管理用のグローバルリスト
clicked_targets = []
clicked_excludes = []
click_history = []  # 操作の順番を記録するリスト

def select_file(title, filetypes):
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title=title, filetypes=filetypes)
    root.destroy()
    return file_path

def save_calibration_json(json_path, num_players, selected_color_names, colors_data):
    """キャリブレーション結果をJSONファイルに書き出す"""
    serializable_data = {}
    for color_name, data in colors_data.items():
        targets = []
        for t in data["targets"]:
            targets.append({
                "hsv_lower": t["hsv_lower"].tolist(),
                "hsv_upper": t["hsv_upper"].tolist(),
                "rgb_lower": t["rgb_lower"].tolist(),
                "rgb_upper": t["rgb_upper"].tolist()
            })
        excludes = []
        for e in data["excludes"]:
            excludes.append({
                "hsv_lower": e["hsv_lower"].tolist(),
                "hsv_upper": e["hsv_upper"].tolist(),
                "rgb_lower": e["rgb_lower"].tolist(),
                "rgb_upper": e["rgb_upper"].tolist()
            })
        serializable_data[color_name] = {
            "box_color": list(data["box_color"]),
            "targets": targets,
            "excludes": excludes
        }
    
    payload = {
        "num_players": num_players,
        "selected_color_names": selected_color_names,
        "detected_colors_data": serializable_data
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=4)
    print(f"[JSON保存] キャリブレーション設定を保存しました: {json_path}")

def load_calibration_json(json_path):
    """JSONファイルからキャリブレーション設定を復元する"""
    with open(json_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    
    num_players = payload["num_players"]
    selected_color_names = payload["selected_color_names"]
    
    loaded_colors_data = {}
    for color_name, data in payload["detected_colors_data"].items():
        targets = []
        for t in data["targets"]:
            targets.append({
                "hsv_lower": np.array(t["hsv_lower"], dtype=np.uint8),
                "hsv_upper": np.array(t["hsv_upper"], dtype=np.uint8),
                "rgb_lower": np.array(t["rgb_lower"], dtype=np.float32),
                "rgb_upper": np.array(t["rgb_upper"], dtype=np.float32)
            })
        excludes = []
        for e in data["excludes"]:
            excludes.append({
                "hsv_lower": np.array(e["hsv_lower"], dtype=np.uint8),
                "hsv_upper": np.array(e["hsv_upper"], dtype=np.uint8),
                "rgb_lower": np.array(e["rgb_lower"], dtype=np.float32),
                "rgb_upper": np.array(e["rgb_upper"], dtype=np.float32)
            })
        loaded_colors_data[color_name] = {
            "box_color": tuple(data["box_color"]),
            "targets": targets,
            "excludes": excludes
        }
    print(f"[JSON読み込み] 既存のキャリブレーション設定をロードしました: {json_path}")
    return num_players, selected_color_names, loaded_colors_data

def select_players_and_colors():
    """人数と色の組み合わせを選択するGUIウィンドウを表示"""
    result = {"players": None, "colors": []}

    root = tk.Tk()
    root.title("人数と色の設定")
    root.geometry("320x430")
    root.resizable(False, False)

    # 1. 人数選択フレーム
    lbl_player = tk.Label(root, text="① 解析する人数を選択してください", font=("Helvetica", 10, "bold"))
    lbl_player.pack(anchor="w", padx=15, pady=(15, 5))

    player_var = tk.IntVar(value=4)
    frame_players = tk.Frame(root)
    frame_players.pack(anchor="w", padx=25)
    
    for p in range(3, 7):
        rb = tk.Radiobutton(frame_players, text=f"{p}人", value=p, variable=player_var)
        rb.pack(side="left", padx=5)

    # 2. 色選択フレーム
    lbl_color = tk.Label(root, text="② 使用する色を人数分選んでください", font=("Helvetica", 10, "bold"))
    lbl_color.pack(anchor="w", padx=15, pady=(15, 5))

    frame_colors = tk.Frame(root)
    frame_colors.pack(anchor="w", padx=25)

    color_vars = {}
    pool_keys = list(ALL_COLOR_POOL.keys())
    
    # デフォルトで最初の4つにチェック
    for i, color_name in enumerate(pool_keys):
        var = tk.BooleanVar(value=(i < 4))
        cb = tk.Checkbutton(frame_colors, text=color_name, variable=var, font=("Helvetica", 9))
        cb.grid(row=i // 2, column=i % 2, sticky="w", padx=10, pady=3)
        color_vars[color_name] = var

    def on_confirm():
        num_p = player_var.get()
        selected_c = [c for c, var in color_vars.items() if var.get()]

        if len(selected_c) != num_p:
            messagebox.showwarning(
                "選択数の不一致", 
                f"選択された人数 ({num_p}人) と色の数 ({len(selected_c)}色) が一致していません。\n{num_p}個の色を選択してください。"
            )
            return

        result["players"] = num_p
        result["colors"] = selected_c
        root.destroy()

    btn_confirm = tk.Button(root, text="決定して進む", command=on_confirm, bg="#4CAF50", fg="white", font=("Helvetica", 10, "bold"), height=2)
    btn_confirm.pack(fill="x", padx=30, pady=20)

    root.mainloop()
    return result["players"], result["colors"]

def compute_normalized_rgb(bgr_img):
    bgr_f = bgr_img.astype(np.float32)
    b, g, r = bgr_f[:, :, 0], bgr_f[:, :, 1], bgr_f[:, :, 2]
    sum_rgb = r + g + b
    sum_rgb[sum_rgb == 0] = 1.0
    return cv2.merge([r / sum_rgb, g / sum_rgb, b / sum_rgb])

def get_unique_video_filename(dir_path, base_name, ext=".mp4"):
    counter = 1
    while True:
        filename = f"{base_name}_{counter:03d}{ext}"
        full_path = os.path.join(dir_path, filename)
        if not os.path.exists(full_path):
            return full_path
        counter += 1

def mouse_click_event(event, x, y, flags, param):
    global clicked_targets, clicked_excludes, click_history
    hsv_img, norm_rgb_img = param
    # 左クリックでターゲット色を追加
    if event == cv2.EVENT_LBUTTONDOWN:
        clicked_targets.append((hsv_img[y, x], norm_rgb_img[y, x]))
        click_history.append('target')
    # 右クリックで除外色を追加
    elif event == cv2.EVENT_RBUTTONDOWN:
        clicked_excludes.append((hsv_img[y, x], norm_rgb_img[y, x]))
        click_history.append('exclude')

def main():
    global clicked_targets, clicked_excludes, click_history, detected_colors_data

    # 1. まず動画ファイルを選択
    video_path = select_file(
        title="解析する動画ファイルを選択してください",
        filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv"), ("All files", "*.*")]
    )
    if not video_path:
        print("動画選択がキャンセルされました。")
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_dir = os.path.dirname(video_path)
    video_base_name = os.path.splitext(os.path.basename(video_path))[0]

    # 2. 既存のJSONファイルを使用するか選択するダイアログを表示
    root = tk.Tk()
    root.withdraw()
    use_existing_json = messagebox.askyesno(
        "キャリブレーション設定の選択",
        "既存のキャリブレーションJSONファイルを使用しますか？\n\n・「はい」: 保存済みのJSONファイルを選択して読み込みます\n・「いいえ」: 新しく手動キャリブレーションを行います"
    )
    root.destroy()

    loaded_success = False

    if use_existing_json:
        # 任意のJSONファイルを選択（初期ディレクトリはスクリプトと同じフォルダ）
        root = tk.Tk()
        root.withdraw()
        json_path = filedialog.askopenfilename(
            title="読み込むキャリブレーションJSONを選択してください",
            initialdir=script_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        root.destroy()

        if json_path and os.path.exists(json_path):
            print("==================================================")
            print(f"【設定ロード】選択されたJSONが見つかりました: {os.path.basename(json_path)}")
            print("キャリブレーションをスキップして解析に進みます。")
            print("==================================================")
            num_players, COLOR_LIST, detected_colors_data = load_calibration_json(json_path)
            loaded_success = True
        else:
            print("JSONファイルが選択されなかったため、新規キャリブレーションに進みます。")

    # 3. JSONが読み込まれなかった場合は手動キャリブレーションを実行
    if not loaded_success:
        # 新しく保存するデフォルトのJSONパス（動画名ベース）
        json_path = os.path.join(script_dir, f"{video_base_name}_calib.json")

        print("==================================================")
        print("【設定入力】人数と色を選択してください...")
        print("==================================================")

        num_players, selected_color_names = select_players_and_colors()
        if not num_players or not selected_color_names:
            print("設定がキャンセルされました。")
            return

        COLOR_CONFIG = {k: ALL_COLOR_POOL[k] for k in selected_color_names}
        COLOR_LIST = list(COLOR_CONFIG.keys())

        print(f"解析人数: {num_players}人")
        print(f"使用色: {', '.join(COLOR_LIST)}")

        calib_image_path = select_file(
            title="キャリブレーション用の画像を選択してください",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp"), ("All files", "*.*")]
        )
        if not calib_image_path: return

        ref_img = cv2.imread(calib_image_path)
        if ref_img is None: return

        hsv_ref = cv2.cvtColor(ref_img, cv2.COLOR_BGR2HSV)
        norm_rgb_ref = compute_normalized_rgb(ref_img)

        win_title = "Calibration Mode"
        cv2.namedWindow(win_title)
        cv2.setMouseCallback(win_title, mouse_click_event, param=(hsv_ref, norm_rgb_ref))

        for color_name in COLOR_LIST:
            box_color = COLOR_CONFIG[color_name]["box_color"]
            h_margin, s_margin, v_margin, rgb_margin = COLOR_CONFIG[color_name]["margins"]
            
            clicked_targets.clear()
            clicked_excludes.clear()
            click_history.clear()
            
            while True:
                debug_calib = ref_img.copy()
                
                target_mask = np.zeros(ref_img.shape[:2], dtype=np.uint8)
                target_data_list = []
                for hsv, rgb in clicked_targets:
                    lower_hsv = np.clip(hsv - [h_margin, s_margin, v_margin], 0, [179, 255, 255]).astype(np.uint8)
                    upper_hsv = np.clip(hsv + [h_margin, s_margin, v_margin], 0, [179, 255, 255]).astype(np.uint8)
                    lower_rgb = np.clip(rgb - rgb_margin, 0.0, 1.0).astype(np.float32)
                    upper_rgb = np.clip(rgb + rgb_margin, 0.0, 1.0).astype(np.float32)
                    
                    m_hsv = cv2.inRange(hsv_ref, lower_hsv, upper_hsv)
                    m_rgb = cv2.inRange(norm_rgb_ref, lower_rgb, upper_rgb)
                    m_combined = cv2.bitwise_and(m_hsv, m_rgb)
                    target_mask = cv2.bitwise_or(target_mask, m_combined)
                    
                    target_data_list.append({
                        "hsv_lower": lower_hsv, "hsv_upper": upper_hsv,
                        "rgb_lower": lower_rgb, "rgb_upper": upper_rgb
                    })

                exclude_mask = np.zeros(ref_img.shape[:2], dtype=np.uint8)
                exclude_data_list = []
                for hsv, rgb in clicked_excludes:
                    lower_hsv = np.clip(hsv - [h_margin, s_margin, v_margin], 0, [179, 255, 255]).astype(np.uint8)
                    upper_hsv = np.clip(hsv + [h_margin, s_margin, v_margin], 0, [179, 255, 255]).astype(np.uint8)
                    lower_rgb = np.clip(rgb - rgb_margin, 0.0, 1.0).astype(np.float32)
                    upper_rgb = np.clip(rgb + rgb_margin, 0.0, 1.0).astype(np.float32)
                    
                    m_hsv = cv2.inRange(hsv_ref, lower_hsv, upper_hsv)
                    m_rgb = cv2.inRange(norm_rgb_ref, lower_rgb, upper_rgb)
                    m_combined = cv2.bitwise_and(m_hsv, m_rgb)
                    exclude_mask = cv2.bitwise_or(exclude_mask, m_combined)
                    
                    exclude_data_list.append({
                        "hsv_lower": lower_hsv, "hsv_upper": upper_hsv,
                        "rgb_lower": lower_rgb, "rgb_upper": upper_rgb
                    })

                combined_mask = cv2.bitwise_and(target_mask, cv2.bitwise_not(exclude_mask))
                
                color_mask = np.zeros_like(ref_img)
                color_mask[:] = (255, 0, 255)
                preview_overlay = cv2.bitwise_and(color_mask, color_mask, mask=combined_mask)
                debug_calib = cv2.addWeighted(debug_calib, 1.0, preview_overlay, 0.5, 0)
                
                contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(debug_calib, contours, -1, (255, 255, 255), 2)
                    
                cv2.putText(debug_calib, f"Target: {color_name}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, box_color, 2)
                cv2.putText(debug_calib, "L-Click: Add | R-Click: Exclude", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                cv2.putText(debug_calib, "U: Undo last click | R: Reset current color | Space: Confirm", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
                cv2.imshow(win_title, debug_calib)
                key = cv2.waitKey(1) & 0xFF
                
                if key == 27:
                    cv2.destroyAllWindows()
                    return
                
                if key == ord('u'):
                    if click_history:
                        last_action = click_history.pop()
                        if last_action == 'target' and clicked_targets:
                            clicked_targets.pop()
                        elif last_action == 'exclude' and clicked_excludes:
                            clicked_excludes.pop()
                
                if key == ord('r'):
                    clicked_targets.clear()
                    clicked_excludes.clear()
                    click_history.clear()

                if key == ord(' ') and clicked_targets:
                    detected_colors_data[color_name] = {
                        "targets": target_data_list,
                        "excludes": exclude_data_list,
                        "box_color": box_color
                    }
                    break
                    
        cv2.destroyWindow(win_title)
        save_calibration_json(json_path, num_players, COLOR_LIST, detected_colors_data)

    # ----------------------------------------------------
    # STEP 3: 動画の判定
    # ----------------------------------------------------
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened(): return

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    sub_w = int(width * SCALE)
    sub_h = int(height * SCALE)
    
    backSub = cv2.createBackgroundSubtractorMOG2(history=30, varThreshold=16, detectShadows=False)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    
    min_area = 500
    min_area_scaled = int(min_area * (SCALE ** 2))
    max_w_scaled = int(MAX_BOX_WIDTH * SCALE)
    max_h_scaled = int(MAX_BOX_HEIGHT * SCALE)

    goal_order = []  
    max_box_sizes = {color: [0, 0] for color in COLOR_LIST}

    tracking_states = {
        color: {
            "prev_cx": None,  
            "prev_cy": None,  
            "vx": 0,          
            "vx_history": [], 
            "w": 0,           
            "h": 0,           
            "lost_count": 0   
        } for color in COLOR_LIST
    }
    MAX_LOST_FRAMES = 120
    AVG_FRAMES = 5        

    output_frames = []
    frame_count = 0

    print("\n[解析開始] 最高速度で解析中...")
    start_time = time.time()  

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break

        frame_count += 1
        frame_resized = cv2.resize(frame, (sub_w, sub_h))

        fg_mask = backSub.apply(frame_resized)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

        if frame_count <= 30:
            cv2.putText(frame, f"--- RANKING (Ready... {frame_count}/30) ---", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 255, 255), 4)
            output_frames.append(frame)
            continue

        hsv_frame = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2HSV)
        norm_rgb_frame = compute_normalized_rgb(frame_resized)

        detected_this_frame_x = {}

        for color_name, data in detected_colors_data.items():
            color_mask = np.zeros(frame_resized.shape[:2], dtype=np.uint8)
            for t_data in data["targets"]:
                mask_hsv = cv2.inRange(hsv_frame, t_data["hsv_lower"], t_data["hsv_upper"])
                mask_norm_rgb = cv2.inRange(norm_rgb_frame, t_data["rgb_lower"], t_data["rgb_upper"])
                m_combined = cv2.bitwise_and(mask_hsv, mask_norm_rgb)
                color_mask = cv2.bitwise_or(color_mask, m_combined)
            
            if data["excludes"]:
                exclude_mask = np.zeros(frame_resized.shape[:2], dtype=np.uint8)
                for e_data in data["excludes"]:
                    mask_ex_hsv = cv2.inRange(hsv_frame, e_data["hsv_lower"], e_data["hsv_upper"])
                    mask_ex_rgb = cv2.inRange(norm_rgb_frame, e_data["rgb_lower"], e_data["rgb_upper"])
                    m_ex_combined = cv2.bitwise_and(mask_ex_hsv, mask_ex_rgb)
                    exclude_mask = cv2.bitwise_or(exclude_mask, m_ex_combined)
                color_mask = cv2.bitwise_and(color_mask, cv2.bitwise_not(exclude_mask))
            
            combined_mask = cv2.bitwise_and(color_mask, fg_mask)
            
            contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            best_contour = None
            max_area = min_area_scaled
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > max_area:
                    max_area = area
                    best_contour = contour

            state = tracking_states[color_name]
            is_estimated = False  

            if best_contour is not None:
                x, y, w, h = cv2.boundingRect(best_contour)
                cx, cy = x + w // 2, y + h // 2
                
                if w > max_box_sizes[color_name][0]: max_box_sizes[color_name][0] = w
                if h > max_box_sizes[color_name][1]: max_box_sizes[color_name][1] = h
                
                w = min(max_box_sizes[color_name][0], max_w_scaled)
                h = min(max_box_sizes[color_name][1], max_h_scaled)
                x = cx - w // 2
                y = cy - h // 2
                
                if state["prev_cx"] is not None and state["lost_count"] == 0:
                    current_vx = cx - state["prev_cx"]
                    state["vx_history"].append(current_vx)
                    
                    if len(state["vx_history"]) > AVG_FRAMES:
                        state["vx_history"].pop(0)
                    
                    state["vx"] = sum(state["vx_history"]) / len(state["vx_history"])
                
                state["prev_cx"] = cx
                state["prev_cy"] = cy
                state["w"] = w
                state["h"] = h
                state["lost_count"] = 0

            else:
                if state["prev_cx"] is not None and state["lost_count"] < MAX_LOST_FRAMES:
                    state["lost_count"] += 1
                    
                    forward_vx = max(0, state["vx"])
                    state["prev_cx"] += int(forward_vx)  
                    cx = state["prev_cx"]
                    
                    cy = state["prev_cy"]
                    w = state["w"]
                    h = state["h"]
                    x = cx - w // 2
                    y = cy - h // 2
                    is_estimated = True
                    
                    state["vx_history"].clear()
                else:
                    continue

            pt_x = int(x + w - (w * 0.1))
            pt_y = int(y + h // 2)
            
            detected_this_frame_x[color_name] = pt_x
            
            x_org, y_org = int(x / SCALE), int(y / SCALE)
            w_org, h_org = int(w / SCALE), int(h / SCALE)
            pt_x_org, pt_y_org = int(pt_x / SCALE), int(pt_y / SCALE)
            
            label = f"{color_name} (Est)" if is_estimated else color_name

            cv2.rectangle(frame, (x_org, y_org), (x_org + w_org, y_org + h_org), data["box_color"], 2)
            cv2.putText(frame, label, (x_org, y_org - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, data["box_color"], 2)
            cv2.circle(frame, (pt_x_org, pt_y_org), 5, (0, 0, 255), -1)

        mid_x = sub_w // 2
        
        for color_name in COLOR_LIST:
            if color_name in detected_this_frame_x:
                pt_x = detected_this_frame_x[color_name]
                if color_name not in goal_order and pt_x > mid_x:
                    inserted = False
                    for i, g_color in enumerate(goal_order):
                        if g_color in detected_this_frame_x:
                            if pt_x > detected_this_frame_x[g_color]:
                                goal_order.insert(i, color_name)
                                inserted = True
                                break
                    if not inserted:
                        goal_order.append(color_name)

        cv2.putText(frame, "--- RANKING ---", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 255), 4)
        for idx, g_color in enumerate(goal_order):
            suffix = "st" if idx == 0 else "nd" if idx == 1 else "rd" if idx == 2 else "th"
            cv2.putText(frame, f"{idx + 1}{suffix}: {g_color}", (20, 140 + idx * 70), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 255), 4)

        output_frames.append(frame)

    cap.release()

    end_time = time.time()
    total_process_time = end_time - start_time
    actual_fps = frame_count / total_process_time if total_process_time > 0 else 0.0

    print("--------------------------------------------------")
    print(f"【解析完了】")
    print(f" 処理フレーム数: {frame_count} frames")
    print(f" 消費時間: {total_process_time:.2f} 秒")
    print(f" 純粋な処理速度: {actual_fps:.1f} FPS 🚀")
    print("--------------------------------------------------")

    if not output_frames:
        print("処理されたフレームがありません。")
        return

    output_filename = get_unique_video_filename(video_dir, f"{video_base_name}_timetruck_json", ext=".mp4")
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(output_filename, fourcc, fps, (width, height))

    print("[動画生成中] 解析データを動画ファイルに書き出しています...")
    for idx, f in enumerate(output_frames):
        video_writer.write(f)
        if (idx + 1) % 100 == 0 or (idx + 1) == len(output_frames):
            print(f" 保存進行度: {idx + 1}/{len(output_frames)} フレーム完了")

    video_writer.release()
    print("==================================================")
    print(f"🎉 動画の保存が完了しました！\n出力先 -> {output_filename}")
    print("==================================================")

if __name__ == "__main__":
    main()