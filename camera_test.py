import cv2

# カメラの初期化（内蔵カメラは通常0）
cap = cv2.VideoCapture(1)

if not cap.isOpened():
    print("カメラを開けませんでした。")
    exit()

while True:
    ret, frame = cap.read()
    
    if not ret:
        print("フレームを取得できませんでした。")
        break

    # 映像を表示
    cv2.imshow('Test Camera', frame)

    # 'q'キーで終了
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()