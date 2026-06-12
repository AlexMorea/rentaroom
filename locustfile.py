from locust import HttpUser, task, between


class RoomsUser(HttpUser):
    wait_time = between(2, 5)

    @task(3)
    def home(self):
        self.client.get("/")

    @task(2)
    def rooms(self):
        self.client.get("/rooms/")

    @task(1)
    def room_detail(self):
        self.client.get("/rooms/1/")