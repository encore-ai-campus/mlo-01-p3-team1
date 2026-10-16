-- 프로젝트 날씨 매핑 전용 스키마. 공통 업무 테이블과 분리.
CREATE SCHEMA IF NOT EXISTS weather_mapping;
CREATE TABLE IF NOT EXISTS weather_mapping.region (
 id TEXT PRIMARY KEY, weather_region_code TEXT, name TEXT NOT NULL,
 address TEXT NOT NULL, nx INTEGER NOT NULL CHECK(nx BETWEEN 1 AND 149),
 ny INTEGER NOT NULL CHECK(ny BETWEEN 1 AND 253), payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS region_weather_code ON weather_mapping.region(weather_region_code);
CREATE TABLE IF NOT EXISTS weather_mapping.road (
 id BIGINT PRIMARY KEY, road_code TEXT NOT NULL, sido TEXT NOT NULL,
 sigungu TEXT NOT NULL, eup_myeon TEXT NOT NULL, name TEXT NOT NULL, search_text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weather_mapping.road_address (
 id BIGINT PRIMARY KEY, address_code TEXT NOT NULL UNIQUE,
 road_id BIGINT NOT NULL REFERENCES weather_mapping.road(id),
 main_no INTEGER NOT NULL, sub_no INTEGER NOT NULL, underground TEXT NOT NULL,
 admin_codes TEXT NOT NULL, admin_names TEXT NOT NULL, weather_region_code TEXT,
 nx INTEGER, ny INTEGER, mapping_status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS road_address_number ON weather_mapping.road_address(road_id,main_no,sub_no);
CREATE TABLE IF NOT EXISTS weather_mapping.metadata (name TEXT PRIMARY KEY,value TEXT NOT NULL);
