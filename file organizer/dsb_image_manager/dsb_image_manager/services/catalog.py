from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ..core.models import ImageRecord


class Catalog:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.initialize()

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY,
                file_path TEXT NOT NULL UNIQUE,
                file_ext TEXT NOT NULL,
                base_name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                pair_group_id TEXT NOT NULL,
                pair_status TEXT NOT NULL,
                display_source TEXT,
                proxy_path TEXT,
                thumbnail_path TEXT,
                capture_datetime TEXT,
                file_modified_datetime TEXT NOT NULL,
                camera_model TEXT,
                lens_model TEXT,
                focal_length TEXT,
                exposure_time TEXT,
                aperture TEXT,
                iso TEXT,
                exposure_compensation TEXT,
                white_balance TEXT,
                color_space TEXT,
                width INTEGER,
                height INTEGER,
                file_size TEXT,
                gps TEXT,
                has_exif INTEGER NOT NULL DEFAULT 0,
                has_proxy INTEGER NOT NULL DEFAULT 0,
                proxy_status TEXT NOT NULL,
                backup_status TEXT NOT NULL DEFAULT 'not_backed_up'
            );

            CREATE TABLE IF NOT EXISTS selection (
                image_id INTEGER PRIMARY KEY,
                pick_status TEXT NOT NULL DEFAULT 'Unrated',
                rating INTEGER NOT NULL DEFAULT 0,
                color_label TEXT NOT NULL DEFAULT '',
                selected INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def upsert_images(self, records: Iterable[ImageRecord]) -> list[ImageRecord]:
        saved: list[ImageRecord] = []
        for record in records:
            saved.append(self.upsert_image(record))
        self.connection.commit()
        return saved

    def upsert_image(self, record: ImageRecord) -> ImageRecord:
        existing = self.connection.execute(
            "SELECT id FROM images WHERE file_path = ?",
            (str(record.file_path),),
        ).fetchone()
        values = self._record_values(record)
        if existing:
            image_id = int(existing["id"])
            self.connection.execute(
                """
                UPDATE images SET
                    file_ext = ?, base_name = ?, media_type = ?, pair_group_id = ?,
                    pair_status = ?, display_source = ?, proxy_path = ?, thumbnail_path = ?,
                    capture_datetime = ?, file_modified_datetime = ?, camera_model = ?,
                    lens_model = ?, focal_length = ?, exposure_time = ?, aperture = ?,
                    iso = ?, exposure_compensation = ?, white_balance = ?, color_space = ?,
                    width = ?, height = ?, file_size = ?, gps = ?, has_exif = ?,
                    has_proxy = ?, proxy_status = ?, backup_status = ?
                WHERE id = ?
                """,
                values[1:] + (image_id,),
            )
        else:
            cursor = self.connection.execute(
                """
                INSERT INTO images (
                    file_path, file_ext, base_name, media_type, pair_group_id,
                    pair_status, display_source, proxy_path, thumbnail_path,
                    capture_datetime, file_modified_datetime, camera_model,
                    lens_model, focal_length, exposure_time, aperture, iso,
                    exposure_compensation, white_balance, color_space, width,
                    height, file_size, gps, has_exif, has_proxy, proxy_status,
                    backup_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            image_id = int(cursor.lastrowid)
            self.connection.execute("INSERT OR IGNORE INTO selection (image_id) VALUES (?)", (image_id,))

        selected = self.connection.execute(
            "SELECT pick_status, rating, color_label, selected, note FROM selection WHERE image_id = ?",
            (image_id,),
        ).fetchone()
        record.id = image_id
        if selected:
            record.pick_status = selected["pick_status"]
            record.rating = int(selected["rating"])
            record.color_label = selected["color_label"]
            record.selected = bool(selected["selected"])
            record.note = selected["note"]
        return record

    def list_images(
        self,
        file_filter: str = "all",
        pick_filter: str = "all",
        sort_key: str = "capture_datetime",
        descending: bool = False,
    ) -> list[ImageRecord]:
        where: list[str] = []
        params: list[object] = []
        if file_filter == "raw":
            where.append("images.media_type = ?")
            params.append("raw")
        elif file_filter == "jpg":
            where.append("images.media_type = ?")
            params.append("jpg")
        elif file_filter == "paired":
            where.append("images.pair_status = ?")
            params.append("raw_jpg_pair")
        elif file_filter == "raw_only":
            where.append("images.pair_status = ?")
            params.append("raw_only")
        elif file_filter == "jpg_only":
            where.append("images.pair_status = ?")
            params.append("jpg_only")
        elif file_filter == "proxy_failed":
            where.append("images.proxy_status = ?")
            params.append("failed")

        if pick_filter != "all":
            where.append("selection.pick_status = ?")
            params.append(pick_filter)

        order_column = {
            "capture_datetime": "COALESCE(images.capture_datetime, images.file_modified_datetime)",
            "file_name": "images.file_path",
            "media_type": "images.media_type",
            "pair_status": "images.pair_status",
            "pick_status": "selection.pick_status",
            "rating": "selection.rating",
            "backup_status": "images.backup_status",
        }.get(sort_key, "COALESCE(images.capture_datetime, images.file_modified_datetime)")
        direction = "DESC" if descending else "ASC"
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.connection.execute(
            f"""
            SELECT images.*, selection.pick_status, selection.rating, selection.color_label,
                   selection.selected, selection.note
            FROM images
            JOIN selection ON selection.image_id = images.id
            {where_sql}
            ORDER BY {order_column} {direction}, images.file_path ASC
            """,
            params,
        ).fetchall()
        return [record_from_row(row) for row in rows]

    def update_selection(
        self,
        image_id: int,
        pick_status: str | None = None,
        rating: int | None = None,
        selected: bool | None = None,
        note: str | None = None,
    ) -> None:
        current = self.connection.execute(
            "SELECT pick_status, rating, selected, note FROM selection WHERE image_id = ?",
            (image_id,),
        ).fetchone()
        if not current:
            self.connection.execute("INSERT INTO selection (image_id) VALUES (?)", (image_id,))
            current = self.connection.execute(
                "SELECT pick_status, rating, selected, note FROM selection WHERE image_id = ?",
                (image_id,),
            ).fetchone()
        self.connection.execute(
            """
            UPDATE selection
            SET pick_status = ?, rating = ?, selected = ?, note = ?
            WHERE image_id = ?
            """,
            (
                pick_status if pick_status is not None else current["pick_status"],
                rating if rating is not None else current["rating"],
                int(selected) if selected is not None else current["selected"],
                note if note is not None else current["note"],
                image_id,
            ),
        )
        self.connection.commit()

    def update_backup_status(self, image_id: int, status: str) -> None:
        self.connection.execute("UPDATE images SET backup_status = ? WHERE id = ?", (status, image_id))
        self.connection.commit()

    def set_setting(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.connection.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    @staticmethod
    def _record_values(record: ImageRecord) -> tuple:
        return (
            str(record.file_path),
            record.file_ext,
            record.base_name,
            record.media_type,
            record.pair_group_id,
            record.pair_status,
            str(record.display_source) if record.display_source else None,
            str(record.proxy_path) if record.proxy_path else None,
            str(record.thumbnail_path) if record.thumbnail_path else None,
            _dt_to_text(record.capture_datetime),
            _dt_to_text(record.file_modified_datetime),
            record.camera_model,
            record.lens_model,
            record.focal_length,
            record.exposure_time,
            record.aperture,
            record.iso,
            record.exposure_compensation,
            record.white_balance,
            record.color_space,
            record.width,
            record.height,
            record.file_size,
            record.gps,
            int(record.has_exif),
            int(record.has_proxy),
            record.proxy_status,
            record.backup_status,
        )


def record_from_row(row: sqlite3.Row) -> ImageRecord:
    return ImageRecord(
        id=int(row["id"]),
        file_path=Path(row["file_path"]),
        file_ext=row["file_ext"],
        base_name=row["base_name"],
        media_type=row["media_type"],
        pair_group_id=row["pair_group_id"],
        pair_status=row["pair_status"],
        display_source=Path(row["display_source"]) if row["display_source"] else None,
        proxy_path=Path(row["proxy_path"]) if row["proxy_path"] else None,
        thumbnail_path=Path(row["thumbnail_path"]) if row["thumbnail_path"] else None,
        capture_datetime=_text_to_dt(row["capture_datetime"]),
        file_modified_datetime=_text_to_dt(row["file_modified_datetime"]) or datetime.fromtimestamp(0),
        camera_model=row["camera_model"] or "",
        lens_model=row["lens_model"] or "",
        focal_length=row["focal_length"] or "",
        exposure_time=row["exposure_time"] or "",
        aperture=row["aperture"] or "",
        iso=row["iso"] or "",
        exposure_compensation=row["exposure_compensation"] or "",
        white_balance=row["white_balance"] or "",
        color_space=row["color_space"] or "",
        width=row["width"],
        height=row["height"],
        file_size=row["file_size"] or "",
        gps=row["gps"] or "",
        has_exif=bool(row["has_exif"]),
        has_proxy=bool(row["has_proxy"]),
        proxy_status=row["proxy_status"],
        backup_status=row["backup_status"],
        pick_status=row["pick_status"],
        rating=int(row["rating"]),
        color_label=row["color_label"] or "",
        selected=bool(row["selected"]),
        note=row["note"] or "",
    )


def _dt_to_text(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _text_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
