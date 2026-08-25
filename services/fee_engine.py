class FeeEngine:


    def __init__(self):

        self.rules = {
            "wallgold": {
                "buy": 0.005,
                "sell": 0.005
            },

            "goldika": {
                "buy": 0.012,
                "sell": 0.012
            }
        }


    def get_fee_percent(self, platform, side):

        rule = self.rules.get(platform)

        if not rule:
            raise Exception(
                f"Unknown platform fee: {platform}"
            )

        return rule[side]


    def calculate_fee(self, platform, side, amount_tmn):

        percent = self.get_fee_percent(
            platform,
            side
        )

        return amount_tmn * percent
