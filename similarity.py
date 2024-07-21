import numpy as np
import pandas as pd
import json
from sklearn.metrics.pairwise import cosine_similarity
from anilist_api import AnilistAPI, AnilistRequestError, AnilistPrivateUser, AnilistUserNotFound


def normalize_ratings(df):
    """
    Normalize the ratings by subtracting the mean rating of each user from their ratings.
    
    Args:
    df (pd.DataFrame): Input DataFrame where rows are users and columns are anime.
    
    Returns:
    pd.DataFrame: Normalized DataFrame with the same shape as the input.
    """
    # Calculate the mean rating for each user
    user_mean_ratings = df.mean(axis=1)
    
    # Subtract the mean rating from each rating
    normalized_df = df.sub(user_mean_ratings, axis=0)
    
    return normalized_df

def cosine_similarity_matrix(df):
    """
    Calculate the cosine similarity matrix for items based on their ratings.
    
    Args:
    df (pd.DataFrame): Input DataFrame where rows are users and columns are items.
    
    Returns:
    pd.DataFrame: Similarity matrix where both rows and columns represent items.
    """
    # Transpose the DataFrame to calculate similarity between items
    df_transposed = df.T
    
    # Calculate cosine similarity
    similarity = cosine_similarity(df_transposed)
    
    # Create a DataFrame from the similarity matrix
    similarity_df = pd.DataFrame(similarity, index=df.columns, columns=df.columns)
    
    return similarity_df

def predict_user_ratings(username, similarity_matrix, api: AnilistAPI):
    """
    Predict ratings for a specified Anilist user's planning list.
    
    Args:
    username (str): The Anilist username.
    similarity_matrix (pd.DataFrame): The item similarity matrix.
    api (AnilistAPI): An instance of the AnilistAPI class.
    
    Returns:
    dict: A dictionary of predicted ratings for the user's planning list.
    """
    try:
        planning = api.fetchPlanningAnime(username=username)
        completed = api.fetchCompletedAnime(usernames=username)
    except (AnilistRequestError, AnilistPrivateUser, AnilistUserNotFound) as e:
        print(f"Error fetching data for user {username}: {str(e)}")
        return {}

    # Convert completed to a Series with anime id as index and score as value
    completed = pd.Series({anime.mediaId: anime.score for anime in completed[username]})

    # Get the subset of the similarity matrix for completed anime and planning anime
    all_anime_sim = similarity_matrix.loc[completed.index, list(planning.keys())]

    predicted_ratings = {}

    for planning_anime, title in planning.items():
        planning_sim = all_anime_sim.loc[:, planning_anime] >= 0
        if planning_sim.sum() > 0:  # Avoid division by zero
            predicted_rating = (planning_sim * completed).sum() / planning_sim.sum()
            predicted_ratings[planning_anime] = {
                'title': title,
                'predicted_rating': predicted_rating
            }
        else:
            predicted_ratings[planning_anime] = {
                'title': title,
                'predicted_rating': None  # or some default value
            }

    return predicted_ratings

api = AnilistAPI()

# Load the ratings data from the JSON file
with open('ratings.json', 'r') as file:
    ratings_data = json.load(file)

# Create a dictionary to store the data
data_dict = {}

# Iterate through the ratings data
for anime_id, ratings in ratings_data.items():
    for rating in ratings:
        for user_id, score in rating.items():
            if user_id not in data_dict:
                data_dict[user_id] = {}
            data_dict[user_id][anime_id] = score

# Create a dataframe from the dictionary
df = pd.DataFrame.from_dict(data_dict, orient='index')

# Convert the index and columns to integers
df.index = df.index.astype(int)
df.columns = df.columns.astype(int)

# Sort the index and columns
df = df.sort_index()
df = df.sort_index(axis=1)

# Print the first few rows and columns of the dataframe
print(df.iloc[:5, :5])

# Print some basic information about the dataframe
print(df.info())

# Print summary statistics of the dataframe
print(df.describe())

norm = normalize_ratings(df)
norm = norm.fillna(0)
sim = cosine_similarity_matrix(norm)
predictions = predict_user_ratings("SimpleCore", sim, api)
