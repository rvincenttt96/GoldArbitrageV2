from adapters.goldika.client import GoldikaClient


if __name__ == "__main__":

    goldika = GoldikaClient(
        username="9362798093",
        password="Rv6047484"
    )

    goldika.login()

    print(goldika.get_price("buy"))
    print(goldika.get_price("sell"))
