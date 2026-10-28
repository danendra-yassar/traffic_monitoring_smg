
from ultralytics import YOLO


class VehicleDetector:
    # COCO class IDs
    VEHICLE_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck

    def __init__(
        self,
        model_path="models/yolov8n.pt",
        confidence=0.25,
        image_size=640,
    ):
        self.model = YOLO(model_path)
        self.confidence = confidence
        self.image_size = image_size

    def detect(self, frame):
        results = self.model.track(
            source=frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=self.VEHICLE_CLASSES,
            conf=self.confidence,
            imgsz=self.image_size,
            verbose=False,
        )

        result = results[0]
        annotated_frame = result.plot()
        vehicles = []

        boxes = result.boxes

        if boxes is None or boxes.id is None:
            return annotated_frame, vehicles

        coordinates = boxes.xyxy.cpu().tolist()
        class_ids = boxes.cls.int().cpu().tolist()
        track_ids = boxes.id.int().cpu().tolist()
        confidences = boxes.conf.cpu().tolist()

        for bbox, class_id, track_id, confidence in zip(
            coordinates, class_ids, track_ids, confidences
        ):
            x1, y1, x2, y2 = bbox

            # Titik tengah bawah bounding box.
            # Lebih sesuai untuk memperkirakan posisi kendaraan di jalan.
            anchor_x = (x1 + x2) / 2
            anchor_y = y2

            vehicles.append({
                "track_id": int(track_id),
                "class_name": self.model.names[class_id],
                "confidence": float(confidence),
                "bbox": [x1, y1, x2, y2],
                "anchor": (anchor_x, anchor_y),
            })

        return annotated_frame, vehicles
