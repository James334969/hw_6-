import os
import re
import time
import urllib.parse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def get_album_id(url):
    clean_url = url.rstrip('/')
    return clean_url.split('/')[-1]

def main():
    print("="*55)
    print(" 35photo.pro 自動下載 CLI (視覺化點擊 + 斷點續傳版) ".center(34))
    print("="*55)
    print("💡 提示：")
    print("1. 下載中隨時按 [Ctrl + C] 可呼叫暫停選單。")
    print("2. 若中斷程式，下次重新執行時會自動跳過已下載的圖片（斷點續傳）。\n")
    
    target_url = input("請輸入 35photo 相簿網址:\n> ").strip()
    if not target_url:
        return

    save_base_path = input("\n請輸入自訂儲存路徑 (預設 ./downloads):\n> ").strip()
    if not save_base_path:
        save_base_path = "./downloads"

    album_id = get_album_id(target_url)
    album_dir = os.path.join(save_base_path, f"35photo_album_{album_id}")
    os.makedirs(album_dir, exist_ok=True)
    print(f"\n[*] 已建立儲存資料夾: {album_dir}\n")

    print("[*] 正在啟動瀏覽器引擎 (本次將開啟視窗以便觀測)...")
    
    try:
        with sync_playwright() as p:
            # 💡 【優化 1】將 headless 改為 False，顯示實體瀏覽器視窗
            # 若有 Cloudflare 防護、18+ 警告、或登入牆，你可以直接在畫面上看到並手動點擊
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                ignore_https_errors=True,
                viewport={'width': 1280, 'height': 800} # 給予足夠大的視窗確保點擊準確
            )
            page = context.new_page()
            
            print("[*] 正在獲取相簿首頁...")
            page.goto(target_url, timeout=60000, wait_until='domcontentloaded')
            
            # 給予 3 秒鐘時間。如果是限制級內容，你可以趁這時候手動點擊「我已滿 18 歲」
            time.sleep(3)
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            photo_page_links = []
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if 'photo_' in href or '/photo/' in href:
                    full_link = urllib.parse.urljoin(target_url, href)
                    if full_link not in photo_page_links:
                        photo_page_links.append(full_link)

            if not photo_page_links:
                print("[!] 找不到任何圖片連結。請確認相簿網址是否正確，或是否需要登入。")
                browser.close()
                input("請按 Enter 鍵結束...")
                return

            # ==========================================
            # 第一階段：解析真實網址 (加入實體點擊模擬)
            # ==========================================
            print(f"[*] 共找到 {len(photo_page_links)} 張圖片。")
            print("[*] 正在執行第一階段：解析真實網址 (請稍候)...\n")
            
            download_queue = []

            for idx, page_url in enumerate(photo_page_links, 1):
                try:
                    # 攜帶 Referer 進入子頁面，避免防盜鏈阻擋
                    page.goto(page_url, timeout=60000, wait_until='domcontentloaded', referer=target_url)
                    
                    # 💡 【優化 2】模擬人類滾動與點擊，觸發 Lazy-load 與高清圖渲染
                    page.evaluate("window.scrollBy(0, 300)") # 向下滾動一點
                    time.sleep(1)
                    
                    # 針對你的提醒：「點擊縮圖才會載入高清原圖」
                    try:
                        # 找尋任何可能是主圖的 img 標籤並點擊
                        page.locator("img").first.click(timeout=3000)
                        time.sleep(1.5) # 等待點擊後的高清 DOM 渲染
                    except:
                        # 若找不到特定圖片，直接點擊畫面正中央盲狙
                        page.mouse.click(640, 400)
                        time.sleep(1.5)
                    
                    # 等待目標特徵出現
                    page.wait_for_selector('div.img-container img', state='attached', timeout=15000)
                    
                    rendered_html = page.content()
                    soup_page = BeautifulSoup(rendered_html, 'html.parser')
                    img_url = None
                    
                    img_container = soup_page.find('div', class_='img-container')
                    if img_container:
                        img_tag = img_container.find('img')
                        if img_tag and img_tag.has_attr('src'):
                            img_url = urllib.parse.urljoin(page_url, img_tag['src'])

                    if img_url:
                        target_filename = img_url.split('/')[-1]
                        clean_filename = f"{idx:03d}_{target_filename}"
                        if '.' not in clean_filename[-6:]:
                            clean_filename += '.jpg'
                            
                        download_queue.append({
                            "idx": idx,
                            "filename": clean_filename,
                            "url": img_url,
                            "referer": page.url
                        })
                        
                        print(f"\r  [+] 解析進度: {idx}/{len(photo_page_links)} 頁就緒...", end="", flush=True)
                    else:
                        print(f"\n  [-] 無法解析第 {idx} 頁的圖片。")
                        
                except Exception as e:
                    print(f"\n  [-] 解析第 {idx} 頁時發生超時。可能是防護阻擋或圖片未成功渲染。")

            print("\n") 
            
            if not download_queue:
                print("[!] 任務清單為空，無法進行下載。")
                browser.close()
                input("請按 Enter 鍵結束...")
                return

            # ==========================================
            # 第二階段：確認視窗
            # ==========================================
            print("\n" + "="*50)
            print(" 📋 下載任務確認報告 ")
            print("="*50)
            print(f" 📂 儲存路徑 : {os.path.abspath(album_dir)}")
            print(f" 🖼️ 照片總數 : {len(download_queue)} 張")
            print("="*50)
            
            confirm = input("\n確認無誤？按 [Enter] 鍵開始下載 (或輸入 'q' 退出): ").strip().lower()
            if confirm == 'q':
                print("\n[*] 已取消任務。")
                browser.close()
                return

            # ==========================================
            # 第三階段：正式下載與進度追蹤
            # ==========================================
            print("\n[*] 開始正式下載...\n")
            
            abort_all = False
            successful_downloads = 0
            skipped_downloads = 0
            failed_downloads = []

            for task in download_queue:
                if abort_all:
                    break
                
                # 💡 【優化 3】斷點續傳機制 (跳過已下載檔案)
                file_path = os.path.join(album_dir, task["filename"])
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    print(f"  [⏭️] 檔案已存在，跳過下載: {task['filename']}")
                    successful_downloads += 1
                    skipped_downloads += 1
                    continue
                
                success = False
                attempt = 1
                max_retries = 3
                
                while attempt <= max_retries and not success:
                    try:
                        response = context.request.get(
                            task["url"],
                            headers={
                                "Referer": task["referer"],
                                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
                            },
                            timeout=30000
                        )

                        if response.ok:
                            img_bytes = response.body()
                            with open(file_path, "wb") as f:
                                f.write(img_bytes)
                            
                            file_size_mb = len(img_bytes) / (1024 * 1024)
                            msg = "成功下載" if attempt == 1 else f"第 {attempt} 次重試成功"
                            print(f"  [✔] {msg}: {task['filename']} ({file_size_mb:.2f} MB)")
                            
                            successful_downloads += 1
                            success = True
                        else:
                            print(f"  [!] HTTP 錯誤，準備重試...")
                            attempt += 1
                            
                    except KeyboardInterrupt:
                        print("\n\n" + "!"*50)
                        print(" [⏸️ 暫停] 偵測到中止指令 (Ctrl + C)")
                        print("!"*50)
                        
                        while True:
                            ans = input("請選擇後續動作？(y=繼續目前下載 / n=結束程式並輸出報告): ").strip().lower()
                            if ans == 'y':
                                print("\n[*] 恢復下載進程 (重新嘗試目前圖片)...\n")
                                break 
                            elif ans == 'n':
                                print("\n[*] 終止下載任務，準備輸出報告...")
                                abort_all = True
                                failed_downloads.append(task["filename"])
                                break
                            else:
                                print("輸入錯誤，請輸入 y 或 n。")
                                
                    except Exception as e:
                        print(f"  [!] 下載發生例外狀況，準備重試...")
                        attempt += 1

                if not success and not abort_all:
                    print(f"  [-] 徹底失敗: {task['filename']}，已達最大重試次數。")
                    failed_downloads.append(task["filename"])

            browser.close()

    except Exception as e:
        print(f"\n[錯誤] 全域執行過程中發生未預期的問題: {e}")

    # ==========================================
    # 第四階段：任務總結報告
    # ==========================================
    print("\n\n" + "="*50)
    print(" 📊 下載任務總結 ")
    print("="*50)
    print(f" 📂 儲存目錄 : {os.path.abspath(album_dir)}")
    print(f" 🎯 總任務數 : {len(download_queue)} 張")
    print(f" ✅ 成功完成 : {successful_downloads} 張 (含斷點跳過 {skipped_downloads} 張)")
    print(f" ❌ 失敗數量 : {len(failed_downloads)} 張")
    
    if failed_downloads:
        print("\n ⚠️ 失敗清單 :")
        for fail_file in failed_downloads:
            print(f"    - {fail_file}")
    print("="*50)
    
    input("\n程式執行完畢，請按 Enter 鍵關閉視窗...")

if __name__ == "__main__":
    main()