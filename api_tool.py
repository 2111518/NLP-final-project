import requests
import re
import json
import math
import os
from geopy.geocoders import Nominatim

# 定義台北市 WMTS 可用的歷史航測與數值地形圖層 (以西元年份為 Key)
AVAILABLE_LAYERS = {
    1947: {"aerial": "Image_1947"},
    1948: {"aerial": "Image_1948"},
    1956: {"aerial": "Image_1956"},
    1958: {"aerial": "Image_1958"},
    1963: {"aerial": "Image_1963"},
    1965: {"aerial": "Image_1965"},
    1967: {"aerial": "Image_1967"},
    1972: {"aerial": "Image_1972"},
    1973: {"aerial": "Image_1973"},
    1991: {"aerial": "Image_1991", "topo": "DGN_M080"}, # 民國 80 年
    2002: {"aerial": "Image_2002", "topo": "DGN_M091"}, # 民國 91 年
    2005: {"aerial": "Image_2005", "topo": "DGN_M094"}, # 民國 94 年
    2007: {"aerial": "Image_2007", "topo": "DGN_M096"}, # 民國 96 年
    2009: {"aerial": "Image_2009", "topo": "DGN_M098"}, # 民國 98 年
    2011: {"aerial": "Image_2011"},
    2012: {"aerial": "Image_2012", "topo": "DGN_M101"}, # 民國 101 年
    2013: {"aerial": "Image_2013", "topo": "DGN_M102"}, # 民國 102 年
    2015: {"aerial": "Image_2015", "topo": "DGN_M104"}, # 民國 104 年
    2017: {"aerial": "Image_2017", "topo": "DGN_M106"}, # 民國 106 年
    2018: {"aerial": "Image_2018"},
    2019: {"aerial": "Image_2019", "topo": "DGN_M108"}, # 民國 108 年
    2020: {"aerial": "Image_2020"},
    2021: {"aerial": "Image_2021", "topo": "DGN_M110"}, # 民國 110 年
    2022: {"aerial": "Image_2022", "topo": "DGN_M111"}, # 民國 111 年
    2023: {"aerial": "Image_2023", "topo": "DGN_M112"}, # 民國 112 年
    2024: {"aerial": "Image_2024", "topo": "DGN_M113"}, # 民國 113 年
    2025: {"aerial": "Image_2025", "topo": "DGN_M114"} # 民國 114 年
}

# 建立一個全域變數作為「快取」，用來儲存下載過的 XML 資料
_WMTS_LAYERS_CACHE = None

def get_wmts_template(layer_id):
    """
    獲取指定圖層的 URL 模板。
    具備快取機制，只會在整個程式第一次執行時下載 XML，後續直接從記憶體讀取。
    """
    global _WMTS_LAYERS_CACHE
    
    # 如果快取是空的，才發送網路請求去下載
    if _WMTS_LAYERS_CACHE is None:
        caps_url = "https://www.historygis.udd.gov.taipei/WMTS/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://historygis.udd.gov.taipei/"
        }
        try:
            res = requests.get(caps_url, headers=headers, timeout=10)
            if res.status_code == 200:
                # 下載成功，將切開的 XML 存入快取
                _WMTS_LAYERS_CACHE = res.text.split("<Layer>")
            else:
                print(f"WMTS 目錄下載失敗，狀態碼: {res.status_code}")
                return None
        except Exception as e:
            print(f"WMTS 連線發生例外錯誤: {e}")
            return None

    # 從快取資料中尋找對應的 Layer ID
    for layer_xml in _WMTS_LAYERS_CACHE:
        if f"<ows:Identifier>{layer_id}</ows:Identifier>" in layer_xml:
            match = re.search(r'template="([^"]+)"', layer_xml)
            if match:
                return match.group(1)         
    return None


def get_dynamic_tile_url(layer_id, z, y, x):
    """
    整合函式：取得模板並替換 XYZ 變數，產生最終的圖磚網址
    """
    template = get_wmts_template(layer_id)
    if not template:
        return None
        
    return template.replace("{Style}", "default") \
                   .replace("{TileMatrixSet}", "GoogleMapsCompatible") \
                   .replace("{TileMatrix}", str(z)) \
                   .replace("{TileRow}", str(y)) \
                   .replace("{TileCol}", str(x))


def latlon_to_tile_xy(lat, lon, zoom=11):
    """座標轉換公式，用來算出 X, Y"""
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return xtile, ytile


def get_taipei_historical_info(base_year: int, location_name: str = None, coord: dict = None) -> str:
    """
    獲取指定地點與基準年份的歷史衛星影像圖磚網址。
    :param base_year: 基準年份 (Agent 判斷的可能年份)
    :param location_name: 欲查詢的地名 (例如："捷運動物園站")
    :param coord: 經緯度字典 (例如：{"latitude": 24.998, "longitude": 121.581})
    """
    # 決定經緯度座標 (優先使用傳入的 coord)
    lat, lon = None, None
    display_name = ""

    if coord and "latitude" in coord and "longitude" in coord:
        lat, lon = coord["latitude"], coord["longitude"]
        display_name = location_name if location_name else f"座標({lat:.4f}, {lon:.4f})"
    elif location_name:
        # 如果只有地名，則呼叫 Geopy 轉換
        geolocator = Nominatim(user_agent="taipei_history_bot")
        location = geolocator.geocode(f"台北市 {location_name}")
        if not location:
            return json.dumps({"status": "error", "message": f"找不到 {location_name} 的座標"}, ensure_ascii=False)
        lat, lon = location.latitude, location.longitude
        display_name = location_name
    else:
        return json.dumps({"status": "error", "message": "必須提供 location_name 或 coord 其中之一。"}, ensure_ascii=False)

    # 2. 轉換為 ArcGIS 的圖磚 X, Y 座標
    zoom_level = 16
    x, y = latlon_to_tile_xy(lat, lon, zoom_level)

    available_years = sorted(AVAILABLE_LAYERS.keys())

    # 拆分成「之前(含當年)」與「之後」兩個陣列
    # 之前：由大到小排序 (越近的排越前面)
    before_years = sorted([y for y in available_years if y <= base_year], reverse=True)
    # 之後：由小到大排序 (越近的排越前面)
    after_years = sorted([y for y in available_years if y > base_year])

    selected_years = []

    # 優先拿 1 個「之後」最近的年份 (如果有的話)
    if after_years:
        selected_years.append(after_years.pop(0))

    # 拿 1 個「之前或當年」最近的年份
    if before_years:
        selected_years.append(before_years.pop(0))

    # 湊滿 3 個圖層：優先從「之前」繼續補，沒有的話再從「之後」補
    if before_years:
        selected_years.append(before_years.pop(0))
    elif after_years:
        selected_years.append(after_years.pop(0))

    # 將最終挑選出來的年份，由舊到新排好，方便 Agent 依序觀看
    selected_years = sorted(selected_years)

    if not selected_years:
        return json.dumps({"status": "error", "message": "找不到任何歷史圖資。"}, ensure_ascii=False)

    historical_images = {}
    numerical_images = {}
    
    for year in selected_years:
        layers = AVAILABLE_LAYERS.get(year, {})
        
        # 解析航測影像 (aerial)
        if "aerial" in layers:
            layer_name = layers["aerial"]
            dynamic_url = get_dynamic_tile_url(layer_name, zoom_level, y, x)
            if dynamic_url:
                historical_images[str(year)] = dynamic_url
                
        # 解析數值地形圖 (topo)
        if "topo" in layers:
            layer_name = layers["topo"]
            dynamic_url = get_dynamic_tile_url(layer_name, zoom_level, y, x)
            if dynamic_url:
                numerical_images[str(year)] = dynamic_url

    result = {
        "status": "success",
        "location_info": {
            "name": display_name,
            "latitude": lat,
            "longitude": lon
        },
        "base_year_requested": base_year,
        "zoom": zoom_level,
        "historical_images": historical_images,
        "numerical_images": numerical_images
    }

    # 把字典轉成 JSON 字串交還給 Agent
    return json.dumps(result, ensure_ascii=False)

# ================= 測試區塊 =================
if __name__ == "__main__":
    print(" 測試開始：呼叫 API 工具...")

    # 情境 1：Agent 只有地名，猜測這張圖是 2015 年
    test_location = "大巨蛋"
    guessed_year = 2015
    print(f"\n 測試情境一：傳入地名 '{test_location}'，基準年份 {guessed_year}")
    json_result_1 = get_taipei_historical_info(base_year=guessed_year, location_name=test_location)
    print("Agent 收到的 JSON 回傳值：\n", json_result_1)

    # 情境 2：Agent 直接傳入座標 (精準度更高)，猜測是 2024 年
    test_coord = {"latitude": 24.9982, "longitude": 121.5793} # 捷運動物園站附近
    guessed_year_2 = 2024
    print(f"\n 測試情境二：傳入座標 {test_coord}，基準年份 {guessed_year_2}")
    json_result_2 = get_taipei_historical_info(base_year=guessed_year_2, coord=test_coord)
    print("Agent 收到的 JSON 回傳值：\n", json_result_2)

    # --- 模擬下載驗證 ---
    data = json.loads(json_result_1)
    if "status" in data and data["status"] == "success":
        print(f"\n 準備模擬 Agent 下載圖片進行驗證...")
        os.makedirs("agent_test_images", exist_ok=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            "Referer": "https://www.historygis.udd.gov.taipei/"
        }

        for year, url in data["historical_images"].items():
            print(f"\n 正在抓取 {year} 年的圖磚...")
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
                    filename = f"agent_test_images/coord_test_{year}.jpg"
                    with open(filename, 'wb') as f:
                        f.write(response.content)
                    print(f" 成功！圖片已存至: {filename}")
                else:
                    print(f" 失敗！狀態碼: {response.status_code}")
            except Exception as e:
                print(f" 網路請求發生錯誤: {e}")

    data = json.loads(json_result_2)
    if "status" in data and data["status"] == "success":
        print(f"\n 準備模擬 Agent 下載圖片進行驗證...")
        os.makedirs("agent_test_images", exist_ok=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            "Referer": "https://www.historygis.udd.gov.taipei/"
        }

        for year, url in data["historical_images"].items():
            print(f"\n 正在抓取 {year} 年的圖磚...")
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
                    filename = f"agent_test_images/coord_test_{year}.jpg"
                    with open(filename, 'wb') as f:
                        f.write(response.content)
                    print(f" 成功！圖片已存至: {filename}")
                else:
                    print(f" 失敗！狀態碼: {response.status_code}")
            except Exception as e:
                print(f" 網路請求發生錯誤: {e}")
