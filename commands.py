import json

f = open("tokens.json")
data = json.load(f)
token = data["StartGG Token"]
url = 'https://api.start.gg/gql/alpha'
header = {"Authorization": "Bearer " + token}

getPlace = """
query EventStandings($event: String!, $page: Int!, $perPage: Int!) {
  event(slug: $event) {
    id
    name
    standings(query: {
      perPage: $perPage,
      page: $page
    }){
      nodes {
        placement
        entrant {
          id
          name
          initialSeedNum
          participants {
            user {
              player {
                prefix
                gamerTag
              }
              discriminator
            }
          }

        }
      }
    }
  }
}
"""

getSets = """
query getSets($event:String!, $page:Int!, $perPage:Int!) {
  event (slug:$event) {
    sets (page:$page, perPage:$perPage) {
      pageInfo {
        page
        perPage
        totalPages
      }
      nodes {
        id
        slots {
          standing {
            stats {
              score {
                value
              }
            }
          }
          entrant {
            id
            name
            participants {
              prefix
              gamerTag
              user {
                discriminator
              }
            }
          }
        }
        winnerId
      }
    }
  }
}
"""