export type Option = {code:string;label:string;type:'theme'|'genre';enabled:boolean};
export type Choices = {region_id:string;vocal_option:string;tempo_preference:string;weather_influence_mode:'ON'|'OFF';selected_theme_codes:string[];selected_genre_codes:string[];option_version:string};
export type Track = {track_id:string;track_name:string;artists_name:string;album_name:string;cover_image_url:string|null;genre_group_codes:string[];theme_codes:string[];scores:{W:string|null;P:string|null;S:string|null}};
export type Playlist = {playlist_id:string;family_id:string;items:Track[];summary:string;generation_method:'RULE_BASED'|'GEMINI_RECONFIGURE';is_test:boolean;preview_only?:boolean;context:{options:Omit<Choices,'region_id'>&{region_id:string|null};excluded_track_ids:string[];weather_code?:string};approval_revision:number;approved_playlist_id:string|null;exclusions_applied:boolean};
export type Exclusions = {family_id:string;excluded_track_ids:string[];revision:number;items:Pick<Track,'track_id'|'track_name'|'artists_name'>[]};
export type FeedbackValue = {value:'LIKE'|'DISLIKE'|number|null;revision:number};
export type Feedback = {source_playlist_id:string;track_reactions:({track_id:string}&FeedbackValue)[];playlist_rating:FeedbackValue};
export type FeedbackRead = {source_playlist_id:string;track_reactions:{track_id:string;reaction:'LIKE'|'DISLIKE'|null;revision:number}[];playlist_rating:{rating:number|null;revision:number}};
