import cv2
import requests
import re
import json

# def get_cctv_url(target_cctv_name="Tugumuda 2"):
def get_cctv_url(target_cctv_name="ARAH TUGU TUNAS"):
    main_url = "https://pantausemar.semarangkota.go.id/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("[1] Mengambil halaman utama PANTAUSEMAR...")
    try:
        response = requests.get(main_url, headers=headers)
        response.raise_for_status()
        
        print("[2] Mencari data array CCTV di dalam HTML...")
        # Regex untuk mengekstrak array JSON dari 'var cctvs = [...];'
        match = re.search(r'var\s+cctvs\s*=\s*(\[.*?\]);', response.text)
        
        if not match:
            print("Gagal menemukan variabel 'cctvs' di dalam HTML.")
            return None
            
        # Mengubah teks yang didapat menjadi objek Python (List of Dictionaries)
        cctvs_json = match.group(1)
        cctvs_data = json.loads(cctvs_json)
        
        print(f"[3] Mencari URL untuk lokasi: '{target_cctv_name}'...")
        # Iterasi seluruh data CCTV untuk mencari nama yang cocok
        for cctv in cctvs_data:
            # Pengecekan nama dibuat lowercase agar tidak case-sensitive
            if cctv.get('owner_name', '').lower() == target_cctv_name.lower():
                links = cctv.get('links', [])
                if links:
                    # Mengambil url dari list 'links' (indeks ke-0)
                    stream_url = links[0].get('url')
                    # Hapus escape slash (\/) dari URL bawaan JSON jika ada
                    stream_url = stream_url.replace('\\/', '/') 
                    return stream_url
                    
        print(f"CCTV dengan nama '{target_cctv_name}' tidak ditemukan di database HTML.")
        return None
        
    except Exception as e:
        print("Terjadi kesalahan:", e)
        return None

# --- Eksekusi Program ---
if __name__ == "__main__":
    # Kamu bisa mengganti ini dengan nama lain, misal: "Simpang Lima 1 360", "Kaligarang", dll.
    # lokasi_cctv = "Tugumuda 2" 
    lokasi_cctv = "ARAH TUGU TUNAS" 
    
    live_url = get_cctv_url(lokasi_cctv)
    
    if live_url:
        print(f"\n[BERHASIL] URL Stream didapat: {live_url}")
        print("Membuka OpenCV viewer (Tekan 'q' pada jendela video untuk keluar)...")
        
        # Buka stream menggunakan OpenCV
        cap = cv2.VideoCapture(live_url)
        
        # Set buffer yang kecil agar minim delay (mirip ffmpeg -fflags nobuffer)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                print("Stream terputus dari server atau selesai.")
                break
                
            # --- Logic YOLOv8 nanti bisa diselipkan di sini ---
            
            # Tampilkan video
            cv2.imshow(f"CCTV - {lokasi_cctv}", frame)
            
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
                
        cap.release()
        cv2.destroyAllWindows()
    else:
        print("\n[GAGAL] Tidak dapat memuat URL stream.")