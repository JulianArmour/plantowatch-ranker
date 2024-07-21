import logging
import time
from collections import namedtuple
from string import Template
from typing import Dict, Generator, List, Union
import json

import requests

class AnilistRequestError(Exception):
    """Custom exception for Anilist API errors"""
    pass

class AnilistPrivateUser(Exception):
    """Custom exception for private Anilist users"""
    pass

class AnilistUserNotFound(Exception):
    """Custom exception for Anilist users not found"""
    pass

AnimeEntry = namedtuple('AnimeEntry', ['mediaId', 'title_romaji', 'score'])

class AnilistAPI:
    """
    A wrapper class for the Anilist GraphQL API.
    """

    def __init__(self):
        self.url = 'https://graphql.anilist.co'
        self.last_request_time = 0
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _rate_limit(self):
        """
        Ensures that requests are made no more frequently than once per second.
        """
        current_time = time.time()
        if current_time - self.last_request_time < 1:
            time.sleep(1 - (current_time - self.last_request_time))
        self.last_request_time = time.time()

    def _make_request(self, query: str, variables: dict) -> dict:
        """
        Makes a rate-limited request to the Anilist GraphQL API.

        Args:
            query (str): The GraphQL query string.
            variables (dict): The variables for the query.

        Returns:
            dict: The JSON response from the API.

        Raises:
            AnilistRequestError: If there's an error in the API response after all retries.
            AnilistPrivateUser: If one of the users in the batch is private.
            AnilistUserNotFound: If one of the users in the batch is not found.
        """
        max_retries = 10
        for attempt in range(max_retries):
            self._rate_limit()
            try:
                response = requests.post(self.url, json={'query': query, 'variables': variables})
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if response.status_code == 404:
                    try:
                        data = response.json()
                    except json.JSONDecodeError:
                        pass  # If it's not a JSON response, it's not our specific error

                    if 'errors' in data:
                        error_message = data['errors'][0].get('message', '')
                        if error_message == 'Private User':
                            users_in_batch = [value for key, value in variables.items() if key.startswith(('username', 'id'))]
                            raise AnilistPrivateUser(f"One of the users provided in the batch {users_in_batch} is private")
                        elif error_message == 'User not found':
                            users_in_batch = [value for key, value in variables.items() if key.startswith(('username', 'id'))]
                            raise AnilistUserNotFound(f"One of the users provided in the batch {users_in_batch} was not found")

                wait_time = 60 * (attempt + 1)  # Backoff strategy: 60s, 120s, 180s, ...
                
                error_msg_parts = [
                    f"Request failed. Retrying in {wait_time} seconds...",
                    f"Error: {str(e)}",
                    f"Status Code: {response.status_code}",
                    f"Response Body: {response.text[:500]}...",  # Truncate long responses
                    "Response Headers:",
                    *[f"  {header}: {value}" for header, value in response.headers.items()]
                ]
                error_msg = "\n".join(error_msg_parts)

                if attempt < max_retries - 1:
                    self.logger.warning(error_msg)
                    time.sleep(wait_time)
                else:
                    self.logger.exception(error_msg)
                    raise AnilistRequestError(f"Failed to make request to Anilist API after {max_retries} attempts: {str(e)}") from e

        raise AnilistRequestError(f"Max retries ({max_retries}) reached")

    def fetchCompletedAnime(self, usernames: Union[str, List[str]] = None, userids: Union[int, List[int]] = None) -> Dict[str, List[AnimeEntry]]:
        """
        Fetches all completed anime scores for one or more users.

        Args:
            usernames (Union[str, List[str]], optional): The username(s) to fetch data for.
            userids (Union[int, List[int]], optional): The user ID(s) to fetch data for.

        Returns:
            Dict[str, List]: A dictionary where keys are usernames/ids and values are lists of AnimeEntry namedtuples.

        Raises:
            ValueError: If neither usernames nor userids are provided, or if both are provided.
            AnilistRequestError: If there's an error in the API response.
            AnilistPrivateUser: If one of the users is private.
            AnilistUserNotFound: If one of the users is not found.
        """
        if (usernames is None and userids is None) or (usernames is not None and userids is not None):
            raise ValueError("Either usernames or userids must be provided, but not both.")

        if isinstance(usernames, str):
            usernames = [usernames]
        if isinstance(userids, int):
            userids = [userids]

        users = usernames or userids
        is_username = usernames is not None

        fragment = '''
        fragment MLG on MediaListGroup {
          entries {
            mediaId
            media {
              title {
                romaji
              }
            }
            score(format: POINT_100)
          }
        }
        '''

        query_template = Template('''
        query UserAnime(${vars}) {
          ${sub_queries}
        }
        ''')

        sub_query_template = Template('''
        u${index}: MediaListCollection(${user_param}: $$${var_name}, type: ANIME, forceSingleCompletedList: true, status: COMPLETED) {
          lists {
            ...MLG
          }
        }
        ''')

        sub_queries = []
        variables = {}
        var_declarations = []

        for i, user in enumerate(users, 1):
            var_name = f"{'username' if is_username else 'id'}{i}"
            var_type = 'String' if is_username else 'Int'
            var_declarations.append(f"${var_name}: {var_type}")
            
            sub_query = sub_query_template.substitute(
                index=i,
                user_param="userName" if is_username else "userId",
                var_name=var_name
            )
            sub_queries.append(sub_query)
            variables[var_name] = user

        query = query_template.substitute(
            vars=', '.join(var_declarations),
            sub_queries='\n'.join(sub_queries)
        )

        query = fragment + query

        response = self._make_request(query, variables)

        result = {}

        for i, user in enumerate(users, 1):
            user_data = response['data'][f'u{i}']
            if user_data is None:
                self.logger.warning(f"No data available for user {user}. They might be private or not found.")
                continue
            entries = []
            for list_entry in user_data['lists']:
                for entry in list_entry['entries']:
                    entries.append(AnimeEntry(
                        mediaId=entry['mediaId'],
                        title_romaji=entry['media']['title']['romaji'],
                        score=entry['score']
                    ))
            result[user] = entries

        return result

    def fetchPlanningAnime(self, userid: Union[int, None] = None, username: Union[str, None] = None) -> Dict[int, str]:
        """
        Fetches all anime in the planning list for a user.

        Args:
            userid (int, optional): The user ID.
            username (str, optional): The username.

        Returns:
            Dict[int, str]: A dictionary where keys are mediaIds and values are anime titles.

        Raises:
            ValueError: If neither userid nor username are provided, or if both are provided.
            AnilistRequestError: If there's an error in the API response.
            AnilistPrivateUser: If the user's list is private.
            AnilistUserNotFound: If the user is not found.
        """
        if (userid is None and username is None) or (userid is not None and username is not None):
            raise ValueError("Either userid or username must be provided, but not both.")

        query = '''
        query UserAnime($id: Int, $username: String) {
          MediaListCollection(userId: $id, userName: $username, type: ANIME, status: PLANNING) {
            lists {
              entries {
                mediaId
                media {
                  title {
                    romaji
                  }
                }
              }
            }
          }
        }
        '''

        variables = {}
        if userid is not None:
            variables['id'] = userid
        else:
            variables['username'] = username

        response = self._make_request(query, variables)

        planning_anime = {}
        if response['data']['MediaListCollection'] is not None:
            for lst in response['data']['MediaListCollection']['lists']:
                for entry in lst['entries']:
                    planning_anime[entry['mediaId']] = entry['media']['title']['romaji']

        return planning_anime

    
    def fetchAnimeCompleters(self, mediaId: int, pages_per_query: int = 5) -> Generator[int, None, None]:
        """
        Finds all users that have completed an anime with the given mediaId.

        Args:
            mediaId (int): The ID of the anime.
            pages_per_query (int): Number of pages to fetch in a single query.

        Yields:
            int: User IDs of users who have completed the anime and given it a non-zero score.

        Raises:
            AnilistRequestError: If there's an error in the API response.
        """
        query_template = Template('''
        query MediaCompleters($mediaID: Int, $perPage: Int, ${page_vars}) {
          ${page_queries}
        }

        fragment mediaListFragment on Page {
          pageInfo {
            currentPage
            hasNextPage
          }
          mediaList(mediaId: $mediaID, status: COMPLETED) {
            userId
            score(format: POINT_100)
          }
        }
        ''')

        page = 1
        while True:
            # Prepare variables and page queries for the current batch
            variables = {'mediaID': mediaId, 'perPage': 50}
            page_vars = []
            page_queries = []
            
            for i in range(pages_per_query):
                current_page = page + i
                page_vars.append(f'page{current_page}: Int')
                page_queries.append(f'p{current_page}: Page(page: $page{current_page}, perPage: $perPage) {{...mediaListFragment}}')
                variables[f'page{current_page}'] = current_page

            # Construct the full query
            query = query_template.substitute(
                page_vars=', '.join(page_vars),
                page_queries='\n'.join(page_queries)
            )

            # Make the request
            response = self._make_request(query, variables)

            # Process the response
            has_next_page = False
            for i in range(pages_per_query):
                current_page = page + i
                page_data = response['data'][f'p{current_page}']
                
                if page_data is None:
                    break

                for entry in page_data['mediaList']:
                    if entry['score'] > 0:
                        yield entry['userId']

                has_next_page = page_data['pageInfo']['hasNextPage']
                if not has_next_page:
                    break

            if not has_next_page:
                break

            page += pages_per_query

