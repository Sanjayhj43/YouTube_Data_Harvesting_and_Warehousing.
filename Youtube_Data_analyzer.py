import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
from pymongo import MongoClient


def build_youtube_client():
    credentials = service_account.Credentials.from_service_account_file(
        "C:/Users/sanja/Downloads/project3-388413-e74139087b18.json",
        scopes=["https://www.googleapis.com/auth/youtube.readonly"]
    )
    youtube = build("youtube", "v3", credentials=credentials)
    return youtube

def get_channel_data(channel_id):
    youtube = build_youtube_client()
    request = youtube.channels().list(
        part="snippet,statistics,contentDetails",
        id=channel_id
    )
    response = request.execute()
    channel = response.get("items", [])[0]
    return channel

def get_video_data(channel_id):
    youtube = build_youtube_client()
    request = youtube.search().list(
        part="id",
        channelId=channel_id,
        maxResults=10  # Adjust the number of videos to retrieve as needed
    )
    response = request.execute()
    video_ids = []
    for item in response.get("items", []):
        video_id = item["id"].get("videoId")
        if video_id:
            video_ids.append(video_id)

    videos = []
    for video_id in video_ids:
        video_request = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=video_id
        )
        video_response = video_request.execute()
        video = video_response.get("items", [])[0]
        videos.append(video)

    return videos


def main():
    st.title("YouTube Channel Analyzer")
    channel_id = st.text_input("Enter YouTube Channel ID:")
    if channel_id:
        if st.button("View Details"):
            channel = get_channel_data(channel_id)
            st.subheader("Channel Information")
            channel_data = {
                "Channel_Name": {
                    "Channel_Name": channel["snippet"]["title"],
                    "Channel_Id": channel_id,
                    "Subscription_Count": channel["statistics"]["subscriberCount"],
                    "Channel_Views": channel["statistics"]["viewCount"],
                    "Channel_Description": channel["snippet"]["description"],
                    "Playlist_Id": channel["contentDetails"].get("relatedPlaylists", {}).get("uploads", "")
                }
            }
            st.write(channel_data)

            videos = get_video_data(channel_id)
            st.subheader("Videos")
            for video in videos:
                video_data = {
                    "Video_Id": {
                        "Video_Id": video["id"],
                        "Video_Name": video["snippet"]["title"],
                        "Video_Description": video["snippet"]["description"],
                        "Tags": video["snippet"].get("tags", []),
                        "PublishedAt": video["snippet"]["publishedAt"],
                        "View_Count": video["statistics"].get("viewCount", 0),
                        "Like_Count": video["statistics"].get("likeCount", 0),
                        "Dislike_Count": video["statistics"].get("dislikeCount", 0),
                        "Favorite_Count": video["statistics"].get("favoriteCount", 0),
                        "Comment_Count": video["statistics"].get("commentCount", 0),
                        "Duration": video["contentDetails"]["duration"],
                        "Thumbnail": video["snippet"]["thumbnails"]["default"]["url"],
                        "Caption_Status": video["contentDetails"].get("caption", "Not Available"),
                        "Comments": {}
                    }
                }
                st.write(video_data)

            if st.button("Save to MongoDB"):
            # Store the data in the MongoDB data lake
                client = MongoClient("mongodb+srv://sanjayhj43:sanju100@cluster1.9ysnezg.mongodb.net/Projectguvi?retryWrites=true&w=majority")
                db = client["Projectguvi"]
                collection = db["Collection1"]

                # Store the channel data
                channel_data = {
                    "Channel_Name": channel["snippet"]["title"],
                    "Channel_Id": channel_id,
                    "Subscription_Count": channel["statistics"]["subscriberCount"],
                    "Channel_Views": channel["statistics"]["viewCount"],
                    "Channel_Description": channel["snippet"]["description"],
                    "Playlist_Id": channel["contentDetails"].get("relatedPlaylists", {}).get("uploads", "")
                }
                collection.insert_one(channel_data)

                # Store the video data
                video_data_list = []
                for video in videos:
                    video_data = {
                        "Video_Id": video["id"],
                        "Video_Name": video["snippet"]["title"],
                        "Video_Description": video["snippet"]["description"],
                        "Tags": video["snippet"].get("tags", []),
                        "PublishedAt": video["snippet"]["publishedAt"],
                        "View_Count": video["statistics"].get("viewCount", 0),
                        "Like_Count": video["statistics"].get("likeCount", 0),
                        "Dislike_Count": video["statistics"].get("dislikeCount", 0),
                        "Favorite_Count": video["statistics"].get("favoriteCount", 0),
                        "Comment_Count": video["statistics"].get("commentCount", 0),
                        "Duration": video["contentDetails"]["duration"],
                        "Thumbnail": video["snippet"]["thumbnails"]["default"]["url"],
                        "Caption_Status": video["contentDetails"].get("caption", "Not Available"),
                        "Comments": {}
                    }
                    video_data_list.append(video_data)
                collection.insert_many(video_data_list)

                # Close the MongoDB connection
                client.close()

                st.success("Data saved to MongoDB!")
                st.write(f"Total documents inserted: {len(video_data_list) + 1}")

if __name__ == "__main__":
    main()

