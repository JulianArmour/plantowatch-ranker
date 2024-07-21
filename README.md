I made this project to test out AI coding, I used claude.ai to generate nearly all the code in this repo.

These script work as a chain of tools to collect a dataset of ratings from users on AniList. `similarity.py` uses a *very* basic memory-based collaborative filtering algorithm. It then ranks items in the user's "plan to watch" list according to the predicted ratings.

Data collection follows this flow: from a seeding user (your username!), collect all their "planned to watch" and "completed" anime. For each of those anime, collect IDs of users who have seen that anime. For each ID in the collected IDs, fetch and save all their completed anime and associated ratings.

To use run this, first run

```bash
python collect_userids.py <your_anilist_username>
```

And then

```bash
python collect_userdata.py --userid-list <output_of_above_script> --checkpoint-file chkpnt.json
```

The checkpoint file is in case data collection is taking a while and you'd like to stop it mid way and start again later.

Finally, to get the ranking

```bash
python similarity.py <username>
```
