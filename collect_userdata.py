import argparse
import json
import logging
import math
from collections import defaultdict
from anilist_api import AnilistAPI, AnilistRequestError, AnilistPrivateUser, AnilistUserNotFound

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_and_store_ratings(user_ids, api, batch_size):
    """
    Fetch anime ratings for given user IDs in batches and store them in the required format.

    Args:
        user_ids (list): List of user IDs to fetch data for.
        api (AnilistAPI): Instance of AnilistAPI to make API calls.
        batch_size (int): Number of users to process in each batch.

    Yields:
        tuple: (ratings dict, remaining users list, last completed batch number)
    """
    ratings = defaultdict(list)
    total_batches = math.ceil(len(user_ids) / batch_size)
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(user_ids))
        batch = user_ids[start_idx:end_idx]

        logger.info(f"Processing batch {batch_num + 1}/{total_batches} (Users {start_idx + 1}-{end_idx})")
        
        try:
            batch_anime = api.fetchCompletedAnime(userids=batch)
        except (AnilistPrivateUser, AnilistUserNotFound) as e:
            logger.warning(f"Error in batch {batch_num + 1}: {str(e)}")
            continue
        except AnilistRequestError as e:
            logger.exception(f"API error in batch {batch_num + 1}: {str(e)}")
            return

        for user_id, user_anime in batch_anime.items():
            for anime in user_anime:
                ratings[str(anime.mediaId)].append({str(user_id): anime.score})

        if (batch_num + 1) % 20 == 0 or batch_num == total_batches - 1:
            remaining_users = user_ids[end_idx:]
            logger.info(f"Processed batch {batch_num + 1}. {len(remaining_users)} users remaining.")
            yield dict(ratings), remaining_users, batch_num

def load_checkpoint(checkpoint_file):
    try:
        with open(checkpoint_file, 'r') as f:
            checkpoint_data = json.load(f)
        return (
            defaultdict(list, checkpoint_data['ratings']),
            checkpoint_data['remaining_users'],
            checkpoint_data['last_batch']
        )
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error(f"Failed to load checkpoint from {checkpoint_file}")
        return None

def save_checkpoint(ratings, remaining_users, last_batch, checkpoint_file):
    checkpoint_data = {
        'ratings': dict(ratings),
        'remaining_users': remaining_users,
        'last_batch': last_batch
    }
    with open(checkpoint_file, 'w') as f:
        json.dump(checkpoint_data, f)

def save_results(ratings, output_file):
    with open(output_file, 'w') as f:
        json.dump(ratings, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description="Fetch and store anime ratings for a list of users")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--userid-list", help="JSON file containing list of user IDs")
    input_group.add_argument("--checkpoint-file", help="File to load checkpoint data from and save to")
    parser.add_argument("--ratings-out", default="ratings.json", help="Output file for storing ratings")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of users to process in each batch")
    args = parser.parse_args()

    # Initialize AnilistAPI
    api = AnilistAPI()

    # Load initial data
    if args.userid_list:
        with open(args.userid_list, 'r') as f:
            user_ids = json.load(f)
        ratings = defaultdict(list)
        last_batch = -1
    else:
        checkpoint_data = load_checkpoint(args.checkpoint_file)
        if checkpoint_data is None:
            logger.error("Failed to load checkpoint. Exiting.")
            return
        ratings, user_ids, last_batch = checkpoint_data

    # Fetch and store ratings
    for updated_ratings, remaining_users, batch_num in fetch_and_store_ratings(user_ids, api, args.batch_size):
        ratings.update(updated_ratings)
        if args.checkpoint_file:
            save_checkpoint(ratings, remaining_users, batch_num, args.checkpoint_file)
            logger.info(f"Checkpoint saved at batch {batch_num + 1}")

    # Save final results
    save_results(ratings, args.ratings_out)
    logger.info(f"Completed. Ratings saved to {args.ratings_out}")

if __name__ == "__main__":
    main()
