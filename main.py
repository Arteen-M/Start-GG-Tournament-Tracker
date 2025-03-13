import requests
import pandas as pd
from commands import *
from trueskill import setup, Rating, rate_1vs1, expose
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import math
import json

# Change the default TrueSkill Environment so that draw probability is 0 (you can't tie in smash bros)
setup(draw_probability=0.0)


# Adds the correct suffix to a number (1st, 2nd, 3rd ...)
def ordinal(place):
    end = "th"
    if (place % 100) in [11, 12, 13]:
        end = "th"
    elif place % 10 == 1:
        end = "st"
    elif place % 10 == 2:
        end = "nd"
    elif place % 10 == 3:
        end = "rd"
    return str(place) + end


# Since discord reads underscores as italics (markdown), use this function to escape those characters
def escape_underscore(s):
    if s.count("_") > 0:  # If there is at least 1 underscore
        if s.count("_") % 2 == 0:  # If there are an even number, we have to escape them all
            return s.replace("_", "\_")
        else:  # If there are an odd number, we escape them all (except for the last one)
            return s.replace("_", "\_", s.count("_", s.count("_")))
    else:
        return s  # If there are 0 underscores, just keep the message the same


def LRFV(x):
    if x == 1:
        return 0
    else:
        return math.floor(math.log(x - 1, 2)) + math.ceil(math.log(2 * x / 3, 2))


# Check for a message exceeding discords character limit (2000 characters)
# This only works assuming each line isn't above 2000 characters long
def message_count(sending):
    if len(sending) >= 1800:  # 1800 for good measure (what if the next line is 200 characters long?)
        send = sending.split("\n")
    else:
        return [sending]  # if the message is short enough to be its own message, we don;t need to do anything else

    # This code splits the messages into a list so it can send multiple times
    s = ["" for x in range(len(send))]  # Creates an empty list of strings
    num_message = 0  # Index to insert the message into
    for line in send:
        s[num_message] += line  # Add lines into the index
        if len(s[num_message]) >= 1800:  # If the index starts getting too big
            num_message += 1  # move the index

    return s[:num_message + 1]  # return the list, but only with the indexes that have non-empty strings


def standard_deviation(lst):
    mean = sum(lst) / len(lst)
    variance = 0
    for x in range(1, len(lst)):
        variance += (lst[x] - mean) ** 2
    variance /= len(lst)
    std = variance ** (1 / 2)
    return std


def table_str(players, row_a, row_b, col_a, col_b):  # inclusive numbers
    names = [p.name for p in players][row_a:row_b + 1]
    name_pad = max(map(len, names)) + 1
    table = " " * name_pad
    extra_spaces = ""

    score_dict = {}

    for c in range(col_a, col_b + 1):  # first row
        if len(names[c]) < 4:
            extra_spaces = " " * (5 - len(names[c]) - 1)
        elif len(names[c]) == 4:
            extra_spaces = " "
        else:
            extra_spaces = ""
        table += "| %s " % (extra_spaces + names[c] + extra_spaces)

    for r in range(row_a, row_b + 1):
        table += '\n' + names[r].ljust(name_pad)
        score_dict[names[r]] = []
        for c in range(col_a, col_b + 1):
            if len(names[c]) < 5:
                if len(names[c]) == 4:
                    add = 5
                else:
                    add = 8 - len(names[c])
            else:
                add = 3
            # add 3 to account for | and space on either side
            # GETSCORE(P1, P2) returns a string like "1 - 5"
            if names[c] != names[r]:
                set_count = str(players[r].head_to_head(names[c].lower()))
                set_count = set_count[1:len(set_count) - 1].replace(",", " -")
                if set_count == "0 - 0":
                    set_count = "x"
            else:
                set_count = "x"
            # table += f"| {set_count}".ljust(len(names[c]) + add)
            table += ("| %s" % set_count).ljust(len(names[c]) + add)
            set_count_display = set_count if '0' in set_count else set_count.replace("-", "=")
            score_dict[names[r]].append(set_count_display)

    df = pd.DataFrame(score_dict, index=names)
    df = df.transpose()
    df.to_csv("PR Table.csv")

    return '`' * 3 + '\n' + table + '`' * 3


def sum_string_across_list(lst, start=0, end=0):
    string_return = ""
    if end == 0:
        e = len(lst)
    else:
        e = end

    for i in range(start, e):
        string_return += lst[i] + " "

    return string_return


class Set:

    def __init__(self, winner, loser, score, tourney, winner_rating=0, loser_rating=0):
        """
        A Class that represents a set played in a tournament


        Attributes:
        -----------
            winner: (Str) Name of the winner of the set
            loser:  (Str) Name of the loser of the set
            score:  (listof Int (len 2)) The score of the set in order [winner_games, loser_games]
            tourney: (Str) Name of the tourney that set was played in

        """

        self.winner = winner
        self.loser = loser
        self.score = score
        self.tourney = tourney
        self.winner_increase = winner_rating
        self.loser_decrease = loser_rating


class Player:
    def __init__(self, name, id):
        self.name = name
        self.id = id
        self.display_name = name
        self.sets = []
        self.set_counts = [0, 0]
        self.win_rate = 0
        self.rating = Rating()
        self.display_rating = 0
        self.rank = 0
        self.prev_rank = 0
        self.season_records = {}
        self.seeding = {}
        self.placement = {}
        self.all_ratings = [0]

    def add_set(self, s):
        self.sets.append(s)  # Put the set into the set list (self.sets)

        # If your name is the winner (your name or in the merged list) and your opponent didn't DQ
        if s.winner.lower() == self.name.lower() and s.score[0] > 1:
            self.set_counts[0] += 1  # Add one to your set wins

        # If you didn't win (your name is not the winner)
        elif s.winner.lower() != self.name.lower():
            self.set_counts[1] += 1  # Add one to your set losses

        # If the addition between set counts isn't 0 (first game is DQ for example)
        if self.set_counts[0] + self.set_counts[1] != 0:
            # Find the win rate in percentage
            self.win_rate = 100 * self.set_counts[0] / (self.set_counts[0] +
                                                        self.set_counts[1])

    def show_sets(self):
        global all_players
        # Creates a message to be sent by the bot later
        message = ""
        current_tourney = ""
        prev_tourney = ""
        uf = 0

        loop_through = self.sets

        # Loop through all sets
        for sets in loop_through:
            current_tourney = sets.tourney
            if current_tourney != prev_tourney:
                prev_tourney = current_tourney
                message += "\n\n" + sets.tourney + ":\n\n"

            if sets.score[1] != -1 and sets.score[0] != 1:
                message += "`" + sets.winner + " Defeats " + sets.loser + " " + str(  # Add each individual set
                    sets.score[0]) + " - " + str(sets.score[1])  # With the names and score

                uf = LRFV(all_players[all_names.index(sets.winner.lower())].seeding[sets.tourney]) - LRFV(
                    all_players[all_names.index(sets.loser.lower())].seeding[sets.tourney])

                if uf > 0:
                    message += "\t[UF: +" + str(uf) + "]`\n"
                else:
                    message += "`\n"

        return message

    def head_to_head(self, opponent):
        set_count = [0, 0]  # start with 0-0 and look across all sets

        for sets in self.sets:
            if sets.winner.lower() == opponent.lower() or sets.loser.lower() == opponent.lower():
                if sets.winner.lower() == opponent.lower():
                    # if you lost, add the set as a win
                    set_count[1] += 1
                else:
                    set_count[0] += 1  # Otherwise, add it as a win

        return set_count  # Return the set count to be used in a discord message later

    def show_results(self):
        message = ""
        check_seeds = self.seeding
        check_place = self.placement

        for tourney in check_seeds:  # Runs through all the tournaments a player has played in
            message += "Seed: %d\nResult: %d\nSPR: %d\n\n" % (
                check_seeds[tourney], check_place[tourney],  # Gets the seed and result of each tournament
                (LRFV(check_seeds[tourney])) - LRFV(check_place[tourney]))

        return message

    def display(self):
        # Creates a message to be sent by the bot later
        # Show name, win rate, set count, average seed, average result and rank if you have one
        name = self.name
        rate = "% " + str(round(self.win_rate, 2))
        count = str(self.set_counts[0]) + "-" + str(self.set_counts[1])
        seed = ordinal(round(sum(self.seeding.values()) / len(self.seeding)))
        # print(name, self.placement.values(), len(self.placement))
        result = ordinal(round(sum(self.placement.values()) / len(self.placement)))
        rank = "Unranked"

        # If you have a rank (0 means unranked)
        if self.rank != 0:
            rank = ordinal(self.rank) + " (" + str(round(self.display_rating)) + ")"

        return name, rate, count, seed, result, rank


all_players = []
all_sets = []


def player_lookup(identifier):
    for player in all_players:
        if type(identifier) == str:
            if identifier.lower() == player.name.lower():
                return player
        else:
            if identifier == player.id:
                return player
    return False


def add_safety(func, *args, entrants=100):
    page = 1
    per_page = entrants

    while True:
        try:
            for x in range(1, page + 1):
                func(args[0], args[1], x, per_page)
            break
        except KeyError:
            page = page * 2 + per_page % 2
            per_page //= 2


def add_placing(name, link, page, per_page):
    placing_query = {
        "event": link,
        "page": page,
        "perPage": per_page
    }

    response = requests.post(url, json={"query": getPlace, "variables": placing_query}, headers=header)
    placements = response.json()['data']['event']['standings']['nodes']
    for entrant in placements:
        find_player = [player_lookup(entrant['entrant']['name']), player_lookup(entrant['entrant']['id'])]
        if not find_player[0] and not find_player[1]:
            player = Player(entrant['entrant']['name'], entrant['entrant']['id'])
            player.placement[name] = entrant['placement']
            all_players.append(player)
        else:
            if find_player[0]:
                find_player[0].placement[name] = entrant['placement']
            else:
                find_player[1].placement[name] = entrant['placement']


def add_seeding(name, phase_id, page, per_page):
    seed_query = {
        "phaseId": phase_id,
        "page": page,
        "perPage": per_page
    }

    response = requests.post(url, json={"query": getSeeds, "variables": seed_query}, headers=header)
    all_seeds = response.json()['data']['phase']['seeds']['nodes']
    for seed in all_seeds:
        if seed['entrant']['participants'][0]['prefix'] is not None and seed['entrant']['participants'][0][
            'prefix'] != "":
            temp_name = seed['entrant']['participants'][0]['prefix'] + " | " + seed['entrant']['participants'][0][
                'gamerTag']
        else:
            temp_name = seed['entrant']['participants'][0]['gamerTag']

        find_player = [player_lookup(temp_name),
                       player_lookup(seed['entrant']['id'])]
        if not find_player[0] and not find_player[1]:
            player = Player(temp_name, seed['entrant']['id'])
            player.seeding[name] = seed['seedNum']
            all_players.append(player)
        else:
            if find_player[0]:
                find_player[0].seeding[name] = seed['seedNum']
            else:
                find_player[1].seeding[name] = seed['seedNum']


def add_sets(name, link, page, per_page):
    set_query = {
        "event": link,
        "page": page,
        "perPage": per_page
    }

    response = requests.post(url, json={"query": getSets, "variables": set_query}, headers=header)
    sets = response.json()['data']['event']['sets']['nodes']

    for s in sets:
        p1 = s['slots'][0]
        p2 = s['slots'][1]
        winner_name = p1['entrant']['name'] if s['winnerId'] == p1['entrant']['id'] else p2['entrant']['name']
        loser_name = p2['entrant']['name'] if s['winnerId'] == p1['entrant']['id'] else p1['entrant']['name']
        p1_score = p1['standing']['stats']['score']['value'] if p1['standing']['stats']['score']['value'] is not None else 0
        p2_score = p2['standing']['stats']['score']['value'] if p2['standing']['stats']['score']['value'] is not None else 0
        score = sorted([p1_score, p2_score], reverse=True)

        new_set = Set(winner_name, loser_name, score, name)
        if score[1] != -1:
            find_winner = player_lookup(winner_name)
            find_loser = player_lookup(loser_name)
            new_set.winner_increase = expose(find_winner.rating)
            new_set.loser_decrease = expose(find_loser.rating)

            find_winner.rating, find_loser.rating = rate_1vs1(find_winner.rating, find_loser.rating)
            new_set.winner_increase = expose(find_winner.rating) - new_set.winner_increase
            new_set.winner_increase *= 100
            new_set.loser_decrease = expose(find_loser.rating) - new_set.loser_decrease
            new_set.loser_decrease *= 100

            find_winner.add_set(new_set)
            find_loser.add_set(new_set)

        all_sets.append(new_set)

    ranks = sorted([player for player in all_players if len(player.sets) > 0], key=lambda a: expose(a.rating),
                   reverse=True)
    for player in all_players:
        player.display_rating = 100 * (expose(player.rating) - expose(ranks[-1].rating))
        if len(player.sets) > 0:
            if player.rank != 0:
                player.prev_rank = player.rank
            player.rank = ranks.index(player) + 1

        player.all_ratings.append(int(player.display_rating))


def add_tournament(name, link, phase_id):
    while True:
        try:
            add_safety(add_placing, name, link)
            break
        except requests.exceptions.JSONDecodeError:
            pass

    while True:
        try:
            add_safety(add_seeding, name, phase_id)
            break
        except requests.exceptions.JSONDecodeError:
            pass

    while True:
        try:
            add_safety(add_sets, name, link)
            break
        except requests.exceptions.JSONDecodeError:
            pass


file_name = "Tournaments/tournaments W25.txt"
f = open(file_name, 'r')
r = f.readlines()
tournaments = []
for line in r:
    tournaments.append(line.strip("\n"))
    line = line.strip("\n").split(",")
    add_tournament(str(line[0]), str(line[1]), int(line[2]))

all_players.sort(reverse=True, key=lambda x: x.display_rating)
all_names = [x.name.lower() for x in all_players]
test_servers = ["Tournament Stats Bot Testing Server", "KingCasual's Server"]

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
client = discord.Client(intents=intents)
f = open("tokens.json")
data = json.load(f)
TOKEN = data["Discord Token"]
# TOKEN = "MTAzMDk4ODg0MDA1NzQ0MjMwNQ.G1Xfn6.ad_lQ8HwpMeoOCVGQ4EG9hUldxxKDRX99SLnWQ"

tree = app_commands.CommandTree(client)

"""
highest = []
for player in all_players:
    spr_lst = []
    for tourney in player.seeding:
        spr = LRFV(player.seeding[tourney]) - LRFV(player.placement[tourney])
        if len(player.seeding) > 1:
            spr_lst.append(spr)

    if len(spr_lst) >= 2:
        sd = standard_deviation(spr_lst)
        highest.append([player.name, spr_lst, sum(spr_lst)/len(spr_lst), sd])

highest.sort(key=lambda x: x[3], reverse=True)
print(highest)
"""


@commands.command()
async def addTournament(ctx):
    global all_names
    l = ctx[5:].split(",")
    add_tournament(str(l[0]), str(l[1]), int(l[2]))
    add_to_file = open(file_name, 'a')
    add_to_file.write("\n" + ctx[5:])
    all_players.sort(reverse=True, key=lambda x: x.display_rating)
    all_names = [x.name.lower() for x in all_players]


@commands.command()
async def showPlayer(ctx):
    index_check = 8

    if ctx.content[index_check:] in all_names:
        play = all_names.index(ctx.content[index_check:])
        name, rate, count, seed, result, rank = all_players[play].display()

        file = discord.File("UW_Smash_Logo_1.png")
        embedVar = discord.Embed(title=name, color=3447003)
        embedVar.add_field(name="Win Rate", value=rate, inline=True)
        embedVar.add_field(name="Set Count", value=count, inline=True)
        embedVar.add_field(name='\u200b', value='\u200b')
        embedVar.add_field(name="Average Seed", value=seed, inline=True)
        embedVar.add_field(name="Average Result", value=result, inline=True)
        embedVar.add_field(name="Current Rank:", value=rank, inline=False)
        embedVar.set_thumbnail(url="attachment://UW_Smash_Logo_1.png")

        await ctx.channel.send(file=file, embed=embedVar)

    else:
        await ctx.channel.send("Not A Valid Player Name!")


@commands.command()
async def resultsEmbed(ctx):
    global all_names, all_players

    index_check = 9

    if ctx.content[index_check:] in all_names:
        play = all_names.index(ctx.content[index_check:])
        tournaments = all_players[play].seeding
        send = all_players[play].show_results()
        to_send = send.split("\n\n")

        file = discord.File("UW_Smash_Logo_1.png")

        pages = []
        for count, tourney in enumerate(tournaments):
            new = discord.Embed(title=tourney + " (%d/%d)" % (count + 1, len(tournaments)))
            new.add_field(name='\u200b', value=escape_underscore(to_send[count]))
            new.set_thumbnail(url="attachment://UW_Smash_Logo_1.png")
            pages.append(new)

        message = await ctx.channel.send(file=file, embed=pages[0])
        await message.add_reaction('⏮')
        await message.add_reaction('◀')
        await message.add_reaction('▶')
        await message.add_reaction('⏭')

        def check(reaction, user):
            return user == ctx.author

        i = 0
        reaction = None

        while True:
            if str(reaction) == '⏮':
                i = 0
                await message.edit(embed=pages[0])
            elif str(reaction) == "◀":
                if i > 0:
                    i -= 1
                    await message.edit(embed=pages[i])
            elif str(reaction) == '▶':
                if i < len(tournaments) - 1:
                    i += 1
                    await message.edit(embed=pages[i])
            elif str(reaction) == '⏭':
                i = len(tournaments) - 1
                await message.edit(embed=pages[i])

            try:
                reaction, user = await client.wait_for('reaction_add', timeout=30.0, check=check)
                await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                break

        await message.clear_reactions()

    else:
        await ctx.channel.send("Not A Valid Player Name!")


# Embed for sets command
@commands.command()
async def setsEmbed(ctx):
    global all_players  # Global list of all players and names

    index_check = 6

    if ctx.content[index_check:] in all_names:  # The player has to be listed in the names list
        play = all_names.index(ctx.content[index_check:])  # take the index of the player in the list
        to_send = all_players[play].show_sets()  # Get the player and the show sets output to work with

        # Split sets by tournaments (show_sets() does this by adding a double enter when a new tournament shows up)
        split_message = to_send.split("\n\n")
        split_message.pop(0)  # The first one is empty
        file = discord.File("UW_Smash_Logo_1.png")

        tournaments = []
        sets_all = []

        # Messages are lists in the format of [tournament, sets, tournament, sets, ...],
        # so every first message is a tournament
        for count, sets in enumerate(split_message):
            if count % 2 == 0:
                tournaments.append(sets)
            else:
                sets_all.append(sets)

        pages = []
        for count, tourney in enumerate(tournaments):
            new = discord.Embed(title=tourney + " (%d/%d)" % (count + 1, len(tournaments)))
            new.add_field(name='\u200b', value=sets_all[count])
            new.set_thumbnail(url="attachment://UW_Smash_Logo_1.png")
            pages.append(new)

        message = await ctx.channel.send(file=file, embed=pages[0])
        await message.add_reaction('⏮')
        await message.add_reaction('◀')
        await message.add_reaction('▶')
        await message.add_reaction('⏭')

        def check(reaction, user):
            return user == ctx.author

        i = 0
        reaction = None

        while True:
            if str(reaction) == '⏮':
                i = 0
                await message.edit(embed=pages[0])
            elif str(reaction) == "◀":
                if i > 0:
                    i -= 1
                    await message.edit(embed=pages[i])
            elif str(reaction) == '▶':
                if i < len(tournaments) - 1:
                    i += 1
                    await message.edit(embed=pages[i])
            elif str(reaction) == '⏭':
                i = len(tournaments) - 1
                await message.edit(embed=pages[i])

            try:
                reaction, user = await client.wait_for('reaction_add', timeout=30.0, check=check)
                await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                break

        await message.clear_reactions()

    else:
        await ctx.channel.send("Not A Valid Player Name!")


@commands.command()
async def headtoHead(ctx):
    index_check = 5

    two = ctx.content[index_check:].split(" = ", maxsplit=1)
    if two[0] in all_names and two[1] in all_names:
        play = all_names.index(two[0])
        play2 = all_names.index(two[1])
        count = all_players[play].head_to_head(two[1])
        send = "The set count between %s and %s is %d - %d" % (
            all_players[play].name, all_players[play2].name, count[0], count[1])
        send = message_count(send)
        for line in send:
            await ctx.channel.send(escape_underscore(line))

        if count[0] == 0 and count[1] == 0:
            await ctx.channel.send("Did you mean '!history h2h'?")

    else:
        await ctx.channel.send("Not Valid Player Name(s)!")


# @commands.command()
# async def ratingsEmbed(ctx, rated, rating_dict):
#     pages = []
#     for rate in rating_dict:
#         new = discord.Embed(title=rated.display_name + " : Rating", description="**" + rate + " " + list(rating_dict[rate].keys())[0] + " / 10**")
#         pfp = rated.display_avatar.url
#         new.set_thumbnail(url=pfp)
#         new.add_field(name='\u200b', value=list(rating_dict[rate].values())[0])
#         pages.append(new)
#
#     message = await ctx.channel.send(embed=pages[0])
#     await message.add_reaction('⏮')
#     await message.add_reaction('◀')
#     await message.add_reaction('▶')
#     await message.add_reaction('⏭')
#
#     def check(reaction, user):
#         return user == ctx.author
#
#     i = 0
#     reaction = None
#
#     while True:
#         if str(reaction) == '⏮':
#             i = 0
#             await message.edit(embed=pages[0])
#         elif str(reaction) == "◀":
#             if i > 0:
#                 i -= 1
#                 await message.edit(embed=pages[i])
#         elif str(reaction) == '▶':
#             if i < len(rating_dict) - 1:
#                 i += 1
#                 await message.edit(embed=pages[i])
#         elif str(reaction) == '⏭':
#             i = len(rating_dict) - 1
#             await message.edit(embed=pages[i])
#
#         try:
#             reaction, user = await client.wait_for('reaction_add', timeout=30.0, check=check)
#             await message.remove_reaction(reaction, user)
#         except asyncio.TimeoutError:
#             break
#
#     await message.clear_reactions()


@commands.command()
async def leaderboardEmbed(ctx, to_send):
    each_player = to_send.split("\n")
    each_player.pop(-1)

    each_player_20 = []
    temp = []
    prev = 0
    for count, player in enumerate(each_player):
        if count // 20 == prev:
            temp.append(player)
        else:
            each_player_20.append(temp)
            temp = [player]
            prev += 1

    if temp:
        each_player_20.append(temp)

    pages = []
    for count, twenty in enumerate(each_player_20):
        new = discord.Embed(title="Leaderboard (%d/%d)" % (count + 1, len(each_player_20)))
        big_string = ""
        for x in twenty:
            big_string += x + "\n"
        new.add_field(name='\u200b', value=escape_underscore(big_string))
        pages.append(new)

    message = await ctx.channel.send(embed=pages[0])
    await message.add_reaction('⏮')
    await message.add_reaction('◀')
    await message.add_reaction('▶')
    await message.add_reaction('⏭')

    def check(reaction, user):
        return user == ctx.author

    i = 0
    reaction = None

    while True:
        if str(reaction) == '⏮':
            i = 0
            await message.edit(embed=pages[0])
        elif str(reaction) == "◀":
            if i > 0:
                i -= 1
                await message.edit(embed=pages[i])
        elif str(reaction) == '▶':
            if i < len(each_player_20) - 1:
                i += 1
                await message.edit(embed=pages[i])
        elif str(reaction) == '⏭':
            i = len(each_player_20) - 1
            await message.edit(embed=pages[i])

        try:
            reaction, user = await client.wait_for('reaction_add', timeout=30.0, check=check)
            await message.remove_reaction(reaction, user)
        except asyncio.TimeoutError:
            break

    await message.clear_reactions()


@client.event
async def on_ready():
    print("Commencing Tournament Tracker Bot. Logged in as {0.user}".format(client))


@client.event
async def on_message(message):
    global all_players

    if message.author == client.user:
        return

    if message.content.startswith("!"):
        original_message = message.content
        message.content = message.content.lower()
        all_cmd = message.content.split()
        all_cmd_upper = original_message.split()
        cmd = message.content.split()[0][1:]
        admin = "Exec" in [y.name.lower() for y in message.author.roles] or message.guild.name in test_servers

        if cmd == "add" and admin:
            if original_message not in tournaments:
                await message.channel.send("Adding, Please Wait")
                await addTournament(original_message)
                await message.channel.send("Finished Adding!")
            else:
                await message.channel.send("Already Added")
        elif cmd == "add":
            await message.channel.send("Incorrect Permissions")

        if cmd == "player":
            await showPlayer(message)

        if cmd == "sets":
            await setsEmbed(message)

        if cmd == "h2h":
            await headtoHead(message)

        if cmd == "results":
            await resultsEmbed(message)

        if cmd == "ty" or message.content[1:] == "thank you":
            await message.channel.send("You're Welcome <3")

        # if cmd == "rate-to":
        #     #for x in client.guilds:
        #     #    print(x, x.id)
        #     #print(message.channel.guild, message.channel.guild.id)
        #     # print(client.guilds)
        #     # print(message.channel.guild)
        #     to = await message.channel.guild.fetch_member(all_cmd[1][2:-1])
        #     rating_file = open("ratings.json", 'r+')
        #     ratings = json.load(rating_file)
        #     ratings[to.name][message.author.name] = {all_cmd[2]: sum_string_across_list(all_cmd_upper, 3)}
        #     rating_file.close()
        #     rating_file = open("ratings.json", 'w')
        #     json.dump(ratings, rating_file, indent=4)
        #
        #     # print(all_cmd[1], all_cmd[1][2:-1])
        #     # to = client.get_user(int(all_cmd[1][2:-1]))
        #     # print(to.name.lower())
        #     # await message.channel.send(all_cmd[1])
        #
        # if cmd == "view-rating":
        #     to = await message.channel.guild.fetch_member(all_cmd[1][2:-1])
        #     rating_file = open("ratings.json")
        #     ratings = json.load(rating_file)
        #     await ratingsEmbed(message, to, ratings[to.name])
        #     rating_file.close()
        #     #for item in ratings[to.name]:
        #     #    print(item)
        #     #    for i in item:
        #     #        print(i)
        #         #item = json.loads(item)
        #         #print(item, item.key(), item.value())

        if cmd == "help":
            help = "Current supported commands:\n- `add [tournament name],[link],[phase id]` add a tournament to the " \
                   "rankings (mod only)\n- `player [player name]` show the overall tournament results of a player\n- " \
                   "`sets [player name]` show the specific sets a player\n- `leaderboard [tournaments (1 if " \
                   "omitted)]` show the current best rated players who played in a minimum number of tournaments.\n- " \
                   "`h2h [player name] = [player name]` shows head-to-head data. Make sure there is a space both " \
                   "before and after an equals sign separating the two players. "
            await message.channel.send(help)

        # if message.content.lower()[1:] == "least consistent player award" and admin:
        #     highest = []
        #     for player in all_players:
        #         spr_lst = []
        #         for tourney in player.seeding:
        #             spr = LRFV(player.seeding[tourney]) - LRFV(player.placement[tourney])
        #             if len(player.seeding) > 1:
        #                 spr_lst.append(spr)
        #
        #         if len(spr_lst) >= 2:
        #             sd = standard_deviation(spr_lst)
        #             highest.append([player.name, sd])
        #
        #     highest.sort(key=lambda x: x[1], reverse=True)
        #
        #     await message.channel.send("The Least Consistent Player Award goes to: %s" % highest[0][0])

        if cmd == "leaderboard":
            if len(all_cmd) > 1:
                num_tournaments = int(all_cmd[1])
            else:
                num_tournaments = 1
            leaderboard = sorted(
                [player for player in all_players if len(player.sets) > 0 and len(player.placement) >= num_tournaments],
                key=lambda a: expose(a.rating), reverse=True)
            messages = ""

            for count, ranking in enumerate(leaderboard):
                if ranking.prev_rank != 0:
                    if ranking.rank < ranking.prev_rank:
                        change = "⬆"
                    elif ranking.rank > ranking.prev_rank:
                        change = "⬇"
                    else:
                        change = ""
                else:
                    change = ""

                messages += "%d %s (%d) %s\n" % (
                    count + 1, ranking.name, ranking.display_rating, change)

            await leaderboardEmbed(message, messages)

        if cmd == "pr-table":
            leaderboard = sorted(
                [p for p in all_players if
                 len(p.placement) >= math.floor(11 / 3)],
                key=lambda a: expose(a.rating), reverse=True)

            #try:
            start_end = message.content[10:].split()
            start = int(start_end[0]) - 1
            end = int(start_end[1]) - 1

            table = table_str(leaderboard, start, end, start, end)
            # print(table)
            await message.channel.send(table)
            # except:
            #    await message.channel.send("Invalid Size Input!")


client.run(TOKEN)
