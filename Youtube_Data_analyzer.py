# [Youtube API libraries]
from googleapiclient.discovery import build
# [MngoDB]
from pymongo import MongoClient
# [SQL library]
import psycopg2
# [Dashboard library]
import streamlit as st
# [File handling]
import re

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["Database name"]
API_KEY = "ENTER YOUR_API_KEY"

# Connect to PostgreSQL
postgres_connection = psycopg2.connect(
    host="localhost",
    port=5432,
    database="your_database",
    user="your_user",
    password="your_password"
)


def parse_duration(duration):
    # (\d+) - one or more digits.
    # ? - makes the preceding element or group in the pattern optional
    # PT,M,S are alphabets as mentioned in the expression inbetween which digits are present
    # PT(hrs)H(mins)M(secs)S
    duration_regex = r'PT((\d+)H)?((\d+)M)?((\d+)S)?'
    matches = re.match(duration_regex, duration)
    # Period of Time timestamp(string) to seconds(int)
    if matches:
        # In this pattern, the first group starts with "(", so it's the number 1.
        # The second group starts with "((", so it's number 2
        # The third group starts after ? & so, it goes on
        hours = int(matches.group(2) or 0)
        minutes = int(matches.group(4) or 0)
        seconds = int(matches.group(6) or 0)
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds

    return 0


# Function to get channel details, video details, and comments
def get_channel_data(youtube, channel_id):
    channel_data = {}

    # Get channel details
    response = youtube.channels().list(
        part="snippet,statistics,contentDetails",
        id=channel_id,
    ).execute()

    if "items" not in response or len(response["items"]) == 0:
        st.error("Invalid channel ID. Please enter a valid channel ID.")
        return None

    channel_info = response["items"][0]
    channel_data["ChannelId"] = channel_id
    channel_data["Channel name"] = channel_info["snippet"]["title"]
    channel_data["Channel description"] = channel_info["snippet"]["description"]
    channel_data["Channel subscriber count"] = channel_info["statistics"]["subscriberCount"]
    channel_data["Channel video count"] = channel_info["statistics"]["videoCount"]
    channel_data["Channel view count"] = channel_info["statistics"]["viewCount"]
    channel_data["PlaylistId"] = channel_info["contentDetails"]["relatedPlaylists"]["uploads"]
    # Get playlist ID for videos
    playlist_id = channel_info["contentDetails"]["relatedPlaylists"]["uploads"]

    # Get video details
    video_ids = []
    video_data = []
    next_page_token = None

    while True:
        request = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()

        for item in response["items"]:
            video_ids.append(item["contentDetails"]["videoId"])

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    for i in range(0, len(video_ids), 50):
        request = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=','.join(video_ids[i:i + 50])
        )
        response = request.execute()

        for video in response["items"]:
            snippet = video.get("snippet", {})
            statistics = video.get("statistics", {})
            content_details = video.get("contentDetails", {})

            video_info = {
                "video_id": video["id"],
                "title": snippet["title"],
                "description": snippet["description"],
                "tags": snippet.get("tags", []),
                "publishedAt": snippet["publishedAt"],
                "thumbnail_url": snippet["thumbnails"]["default"]["url"],
                "viewCount": statistics.get("viewCount", 0),
                "likeCount": statistics.get("likeCount", 0),
                "favoriteCount": statistics.get("favoriteCount", 0),
                "commentCount": statistics.get("commentCount", 0),
                "duration": content_details.get("duration", ""),
                "definition": content_details.get("definition", ""),
                "caption": content_details.get("caption", "")
            }

            video_data.append(video_info)

    # Get comments for each video
    for video in video_data:
        video_id = video["video_id"]
        video["Comments"] = []

        try:
            next_page_token = None

            while True:
                request = youtube.commentThreads().list(
                    part="snippet,replies",
                    videoId=video_id,
                    maxResults=100,
                    pageToken=next_page_token
                )
                response = request.execute()

                for item in response["items"]:
                    comment_id = item["id"]
                    comment = item["snippet"]["topLevelComment"]["snippet"]["textOriginal"]
                    comment_author = item["snippet"]["topLevelComment"]["snippet"]["authorDisplayName"]
                    published_at = item["snippet"]["topLevelComment"]["snippet"]["publishedAt"]

                    reply_texts = []
                    for reply in item.get("replies", {}).get("comments", []):
                        reply_text = reply["snippet"]["textOriginal"]
                        reply_texts.append(reply_text)

                    comment_info = {
                        "Comment_Id": comment_id,
                        "Comment_Text": comment,
                        "Comment_Author": comment_author,
                        "Comment_PublishedAt": published_at,
                        "Replies": reply_texts
                    }

                    video["Comments"].append(comment_info)

                if "nextPageToken" in response:
                    next_page_token = response["nextPageToken"]
                else:
                    break

        except Exception as e:
            # Handle the exception when comments are disabled
            print(f"Failed to retrieve comments for video ID: {video_id}")
            print(f"Error message: {str(e)}")
            continue

    channel_data["Videos"] = video_data

    return channel_data


# Function to migrate data to MongoDB
def migrate_data_to_mongodb(channel_id):
    youtube = build("youtube", "v3", developerKey=API_KEY)
    channel_data = get_channel_data(youtube, channel_id)
    channels_collection = db["migrated_channels"]
    # channels_collection.insert_one(channel_data)
    # return channel_data

    # Check if channel data already exists
    existing_data = channels_collection.find_one({"ChannelId": channel_id})

    if existing_data:
        # Update the existing channel data
        channels_collection.update_one({"ChannelId": channel_id}, {"$set": channel_data})
    else:
        # Insert the new channel data
        channel_data["ChannelId"] = channel_id
        channels_collection.insert_one(channel_data)


# Function to migrate data from MongoDB to PostgreSQL
def migrate_data_to_sql(channel_id):
    # Retrieve channel data from MongoDB
    channel_data = db["migrated_channels"].find_one({"ChannelId": channel_id})

    if channel_data:
        # Check if channel data already exists
        with postgres_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM channel WHERE channel_id = %s", (channel_id,))
            result = cursor.fetchone()
            if result[0] > 0:
                st.write("Channel data already exists in PostgreSQL. Migrating updated channel data")
                # Uses "ON DELETE CASCADE" to delete all corresponding details of given channel id
                cursor.execute("DELETE FROM channel WHERE channel_id= %s", (channel_id,))

        # Insert channel data into PostgreSQL
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO channel (channel_id, channel_name, channel_views, channel_description) "
                "VALUES (%s, %s, %s, %s)",
                (
                    channel_data["ChannelId"],
                    channel_data["Channel name"],
                    int(channel_data["Channel view count"]),
                    channel_data["Channel description"]
                )
            )
            cursor.execute(
                "INSERT INTO playlist (playlist_id,channel_id)"
                "VALUES (%s, %s)",
                (
                    channel_data["PlaylistId"],
                    channel_data["ChannelId"]
                )
            )
        # Insert video data into PostgreSQL
        for video in channel_data["Videos"]:
            duration_seconds = parse_duration(video["duration"])
            with postgres_connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO video (video_id, playlist_id, video_name, video_description, published_date, "
                    "view_count, like_count, favorite_count, comment_count, duration, thumbnail, caption_status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        video["video_id"],
                        channel_data["PlaylistId"],
                        video["title"],
                        video["description"],
                        video["publishedAt"],
                        int(video["viewCount"]),
                        int(video["likeCount"]),
                        int(video["favoriteCount"]),
                        int(video["commentCount"]),
                        duration_seconds,
                        video["thumbnail_url"],
                        video["caption"]
                    )
                )

            # Insert comment data into PostgreSQL
            for comment in video["Comments"]:
                with postgres_connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO comment (comment_id, video_id, comment_text, comment_author, comment_published_date) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (
                            comment["Comment_Id"],
                            video["video_id"],
                            comment["Comment_Text"],
                            comment["Comment_Author"],
                            comment["Comment_PublishedAt"]
                        )
                    )

        postgres_connection.commit()
        st.write("Data migrated to PostgreSQL")
    else:
        st.error("No data found for the provided channel ID")


# Streamlit app
def main():
    # YouTube service client setup
    api_service_name = "youtube"
    api_version = "v3"
    youtube = build(api_service_name, api_version, developerKey=API_KEY)

    # ============    /   Configuring Streamlit GUI   /    ============    #

    st.set_page_config(layout='wide')
    # Title
    st.title(":red[YouTube] :orange[Data API and :red[Streamlit] Demo]")
    # columns for fetching & migration
    col1, col2 = st.columns(2)

    # ===============    /   Data Fetch Section   /    ================    #

    with col1:
        st.header(':orange[Data collection]')
        st.write('''**Get :red[YouTube] channel details by entering valid channel_id**''')
        # User input of channel_id
        channel_id = st.text_input("Enter Channel ID")
        st.write(
            '''Click the **:blue['Get Channel Data']** button to get the channel details of the required channel_id.''')
        if st.button(":green[Get Channel Data]"):
            channel_data = get_channel_data(youtube, channel_id)
            st.json(channel_data)

    # ===============    /   Migration Section   /    ================    #

    # # Retrieve existing channel IDs from MongoDB
    existing_channel_ids = [item["ChannelId"] for item in db["migrated_channels"].find()]
    with col2:
        st.header(':orange[Data migration]')
        st.write('''**Choose channel_id(s) from dropdown to store :red[YouTube] channel details**''')
        # Retrieve existing channel IDs from MongoDB
        # existing_channel_ids = [item["ChannelId"] for item in db["migrated_channels"].find()]

        # Initialize the 'fetched_channel_ids' key with an empty list if it doesn't exist
        fetched_channel_ids = st.session_state.setdefault('fetched_channel_ids', [])

        # Convert fetched_channel_ids to a list if it's a string
        # since channel_id is string & fetched_channel_ids need to be a list for ids to be appended
        if isinstance(fetched_channel_ids, str):
            fetched_channel_ids = [fetched_channel_ids]

        # Check if the channel ID is not already in fetched_channel_ids
        # Add the channel_id to the 'fetched_channel_ids' list
        if channel_id not in fetched_channel_ids:
            fetched_channel_ids.append(channel_id)

        # Store the updated 'fetched_channel_ids' list in session state
        st.session_state['fetched_channel_ids'] = fetched_channel_ids

        # Store channel IDs in a multi-selectable dropdown
        selected_channel_ids = st.multiselect("Select Channel IDs to migrate",
                                              st.session_state.get('fetched_channel_ids', []))
        st.write(''':red[*Click on **:blue['Migrate to MongoDB']** to save in **MongoDB**]''')
        st.write(''':red[*Click on **:blue['Migrate to SQL']** to save in **SQL**]''')
        if st.button(":green[Migrate to MongoDB]"):
            for selected_id in selected_channel_ids:
                try:
                    migrate_data_to_mongodb(selected_id)
                    st.write(f"Data migrated to MongoDB for Channel ID: {selected_id}")
                    # existing_channel_ids.remove(selected_id)  # Remove migrated channel ID from the list
                except ValueError as e:
                    st.error(str(e))

        if st.button(":green[Migrate to SQL]"):
            for selected_id in selected_channel_ids:
                try:
                    migrate_data_to_sql(selected_id)
                    st.write(f"Data migrated to PostgreSQL for Channel ID: {selected_id}")
                except Exception as e:
                    st.error("Error occurred during migration: {}".format(str(e)))

    # ==================    /   Query Section   /    ===================    #

    # Define the SQL queries
    queries = {
        "1. What are the names of all the videos and their corresponding channels?": """
            SELECT video_name, channel_name
            FROM video
            JOIN playlist ON video.playlist_id = playlist.playlist_id
            JOIN channel ON playlist.channel_id = channel.channel_id
        """,
        "2. Which channels have the most number of videos, and how many videos do they have?": """
            SELECT c.channel_name, COUNT(v.video_id)
            FROM channel c
            JOIN playlist p ON c.channel_id = p.channel_id
            JOIN video v ON p.playlist_id = v.playlist_id
            GROUP BY c.channel_name
            HAVING COUNT(v.video_id) = (
                SELECT COUNT(video_id) AS video_count
                FROM channel
                JOIN playlist ON channel.channel_id = playlist.channel_id
                JOIN video ON playlist.playlist_id = video.playlist_id
                GROUP BY channel_name
                ORDER BY video_count DESC
                LIMIT 1
            )
        """,
        "3. What are the top 10 most viewed videos and their respective channels?": """
                SELECT video.video_name, channel_name, video.view_count
                FROM channel
                JOIN playlist ON channel.channel_id = playlist.channel_id
                JOIN video ON playlist.playlist_id = video.playlist_id
                ORDER BY view_count DESC
                LIMIT 10
            """,
        "4. How many comments were made on each video, and what are their corresponding video names?": """
                    SELECT video_name, COUNT(comment_id) AS comment_count
                    FROM video
                    JOIN comment ON video.video_id = comment.video_id
                    GROUP BY video_name
                    ORDER BY comment_count DESC
                """,
        "5. Which videos have the highest number of likes, and what are their corresponding channel names?": """
                    SELECT video.video_name, channel.channel_name
                    FROM channel
                    JOIN playlist ON channel.channel_id = playlist.channel_id
                    JOIN video ON playlist.playlist_id = video.playlist_id
                    where like_count = (select max(like_count) from video)
                """,
        "6. What is the total number of likes and favorites for each video, and what are their corresponding video names?": """
                    SELECT video_name, like_count, favorite_count
                    FROM video
                    ORDER BY like_count DESC, favorite_count DESC
                """,
        "7. What is the total number of views for each channel, and what are their corresponding channel names?": """
                    SELECT channel_name,channel_views
                    FROM channel
                    ORDER BY channel_views DESC
                """,
        "8. What are the names of all the channels that have published videos in the year 2022?": """
                    SELECT DISTINCT(channel_name)
                    FROM channel
                    JOIN playlist ON channel.channel_id = playlist.channel_id
                    JOIN video ON playlist.playlist_id = video.playlist_id
                    WHERE EXTRACT(YEAR FROM video.published_date) = 2022
                """,
        "9. What is the average duration of all videos in each channel, and what are their corresponding channel names?": """
                    SELECT channel_name, AVG(duration)
                    FROM channel
                    JOIN playlist ON channel.channel_id = playlist.channel_id
                    JOIN video ON playlist.playlist_id = video.playlist_id
                    GROUP BY channel_name
                    ORDER BY AVG(duration) DESC
                """,
        "10. Which videos have the highest number of comments, and what are their corresponding channel names?": """
                    SELECT video_name, channel_name
                    FROM channel
                    JOIN playlist ON channel.channel_id = playlist.channel_id
                    JOIN video ON playlist.playlist_id = video.playlist_id
                    where comment_count = (select max(comment_count) from video)
                """
    }

    # Sidebar section
    st.sidebar.header(':violet[Question Section]')

    # Create a dropdown menu to select the question
    selected_question = st.sidebar.selectbox("Select a question", list(queries.keys()))

    if st.sidebar.button(":green[Display Data]"):
        # Execute the selected query
        selected_query = queries[selected_question]
        with postgres_connection.cursor() as cursor:
            cursor.execute(selected_query)
            results = cursor.fetchall()

        # Display the query results
        if results:
            st.sidebar.table(results)
        else:
            st.write("No results found.")


if __name__ == "__main__":
    main()
