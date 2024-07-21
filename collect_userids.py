import argparse
import json
import time
from collections import deque
from anilist_api import AnilistAPI

def main():
    # Create argument parser
    parser = argparse.ArgumentParser(description="Fetch Anilist users based on a seed username")
    parser.add_argument("username", help="The username to seed from")
    parser.add_argument("--n-others", type=int, default=100, help="The number of other users to fetch per anime")
    parser.add_argument("--other-users-out", default="other_users.json", help="File to output the other users IDs")
    args = parser.parse_args()

    # Initialize AnilistAPI
    api = AnilistAPI()

    # Fetch completed and planning anime for the seed user
    user_completed = api.fetchCompletedAnime(usernames=args.username)[args.username]
    user_planning = api.fetchPlanningAnime(username=args.username)

    # Merge the IDs from completed and planning anime into a single set
    search_set = set(anime.mediaId for anime in user_completed)
    search_set.update(user_planning.keys())

    other_users = set()  # set of users that have also seen anime on our list
    
    # Initialize time tracking
    iteration_times = deque(maxlen=10)
    start_time = time.time()

    for i, anime_id in enumerate(search_set, 1):
        iteration_start = time.time()
        
        # Get the title from either completed or planning list
        anime_title = next((anime.title_romaji for anime in user_completed if anime.mediaId == anime_id), 
                           user_planning.get(anime_id, "Unknown Title"))
        
        users_added = 0
        for j, other_user in enumerate(api.fetchAnimeCompleters(mediaId=anime_id), 1):
            other_users.add(other_user)
            users_added += 1
            
            # Print progress as whole number percentage
            percentage = (users_added * 100) // args.n_others
            if percentage > 0 and users_added % (args.n_others // 100) == 0:
                print(f"  Processed {percentage}% of users for this anime")
            
            if users_added >= args.n_others:
                break
        
        iteration_end = time.time()
        iteration_times.append(iteration_end - iteration_start)
        
        # Calculate and print progress with time estimate
        avg_iteration_time = sum(iteration_times) / len(iteration_times)
        remaining_iterations = len(search_set) - i
        estimated_time_remaining = (remaining_iterations * avg_iteration_time) / 60  # in minutes
        
        print(f"Progress: {i}/{len(search_set)} - Anime: {anime_title}")
        print(f"Estimated time remaining: {estimated_time_remaining:.2f} minutes")

    # Output other_users to the specified file as a JSON list
    with open(args.other_users_out, 'w') as f:
        json.dump(list(other_users), f)

    total_time = (time.time() - start_time) / 60  # in minutes
    print(f"Completed. Found {len(other_users)} unique users. Data saved to {args.other_users_out}")
    print(f"Total time taken: {total_time:.2f} minutes")

if __name__ == "__main__":
    main()
