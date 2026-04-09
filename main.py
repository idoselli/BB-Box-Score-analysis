#!/usr/bin/env python3

import argparse
from pathlib import Path
import requests
import xml.etree.ElementTree as XML
from tabulate import tabulate, SEPARATING_LINE

from game import *
from event import *
from player import Player
from team import Team
from bbapi import *


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "matches"


def parse_report(report: str, at: Team, ht: Team) -> list[BBEvent]:
    events = []

    # Read players
    i = 0
    index = 0
    while i < 96:
        id = int(report[i : i + 8])
        i += 8

        if index < len(ht.players):
            ht.players[index].id = id
        index += 1

    index = 0
    while i < 192:
        id = int(report[i : i + 8])
        i += 8

        if index < len(at.players):
            at.players[index].id = id
        index += 1

    # Read starters
    pos = 0
    while i < 197:
        id = int(report[i], 16) - 1
        if __debug__:
            print("starter: ", id, f"{ht.players[id]}")
        ht.set_starter(id, pos)
        i += 1
        pos += 1
    pos = 0
    while i < 202:
        id = int(report[i], 16) - 1
        if __debug__:
            print("starter: ", id, f"{at.players[id]}")
        at.set_starter(id, pos)
        i += 1
        pos += 1

    # Read events
    while i < len(report):
        s = report[i : i + 17]

        e = BBEvent(
            team=int(s[0]),
            type=int(s[1:4]),
            result=int(s[4], 16),
            variation=int(s[6], 16),
            player1=int(s[7], 16),
            player2=int(s[8], 16),
            gameclock=int(s[9:13]),
            realclock=int(s[13:17]),
            data=s[1:9],
        )

        sub_type = e.type // 100
        if int(s[5]) > 0:
            e.type = -100
            e.result = 0
            sub_type = 99

        events.append(e)

        if sub_type in (1, 2, 4):
            n = BBEvent(
                team=e.team,
                type=0,
                variation=0,
                result=e.result,
                player1=e.player1,
                player2=e.player2,
                gameclock=e.gameclock.clock,
                realclock=e.realclock + 2,
                data="",
            )

            if n.result > 9:
                n.result -= 9
            if e.result > 9:
                n.data = "000{}0000".format(e.result - 9)
            else:
                n.data = "000{}0000".format(e.result)

            events.append(n)

        i += 17

    return events


def parse_xml(text: str) -> tuple[list[BBEvent], Team, Team]:
    tree = XML.ElementTree(XML.fromstring(text))
    root = tree.getroot()

    ht = Team()
    at = Team()
    report = ""

    for child in root:
        tag = child.tag
        if tag == "HomeTeam":
            for team in child:
                if team.tag == "ID":
                    assert team.text, "Missing team ID"
                    ht.id = int(team.text)
                elif team.tag == "Name":
                    assert team.text, "Missing team name"
                    ht.name = team.text
                elif team.tag == "ShortName":
                    assert team.text, "Missing team short name"
                    ht.short = team.text
        elif tag == "AwayTeam":
            for team in child:
                if team.tag == "ID":
                    assert team.text
                    at.id = int(team.text)
                elif team.tag == "Name":
                    assert team.text
                    at.name = team.text
                elif team.tag == "ShortName":
                    assert team.text
                    at.short = team.text
        elif tag.startswith("HPlayer") and not tag.startswith("HPlayerNick"):
            assert child.text, "Missing HPlayer string"
            p = Player()
            p.name = child.text
            ht.players.append(p)
        elif tag.startswith("APlayer") and not tag.startswith("APlayerNick"):
            assert child.text, "Missing APlayer string"
            p = Player()
            p.name = child.text
            at.players.append(p)
        elif tag == "ReportString":
            assert child.text, "Missing report string"
            report = child.text.strip()

    # Fill upto 12 players with empty objects, as the events events apparently reference these.
    while len(ht.players) < 12:
        ht.players.append(Player("Lucky Fan"))
    while len(at.players) < 12:
        at.players.append(Player("Lucky Fan"))

    events = parse_report(report, at, ht)

    return (events, ht, at)


def get_xml_text(matchid) -> str:
    path = CACHE_DIR / f"report_{matchid}.xml"

    if path.exists():
        return path.read_text(encoding="utf-8")

    data = requests.get(
        f"https://buzzerbeater.com/match/viewmatch.aspx?matchid={matchid}"
    )
    data.raise_for_status()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data.text, encoding="utf-8")
    except OSError:
        pass

    return data.text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matchid", help="Match ID", required=True)
    parser.add_argument("--username", help="BBAPI username")
    parser.add_argument("--password", help="BBAPI password")
    parser.add_argument("--print-events", action="store_true")
    parser.add_argument("--print-stats", action="store_true")
    parser.add_argument("--save-charts", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    text = get_xml_text(args.matchid)
    events, ht, at = parse_xml(text)
    game = Game(args.matchid, events, ht, at, args, [])
    game.play()
    game.save(f"{args.matchid}.json")


if __name__ == "__main__":
    main()
