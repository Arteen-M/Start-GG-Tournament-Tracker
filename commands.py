token = '1a2d00e165d4341d4ce83efabff3db90'
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
          }
        }
        winnerId
      }
    }
  }
}
"""

getSeeds = """
query PhaseSeeds($phaseId: ID!, $page: Int!, $perPage: Int!) {
  phase(id:$phaseId) {
    id
    seeds(query: {
      page: $page
      perPage: $perPage
    }){
      pageInfo {
        total
        totalPages
      }
      nodes {
        id
        seedNum
        entrant {
          id
          participants {
            id
            prefix
            gamerTag
          }
        }
      }
    }
  }
}
"""
# Phase ID is the first number after the link
# EX: https://www.start.gg/tournament/uwaterloo-ultimate-fall-2023-week-2-electric-boogaloo/event/ultimate-singles
# /brackets/1469093/2221901 1469093 is the PhaseID
