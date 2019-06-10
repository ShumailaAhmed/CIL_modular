class configDrive:
    def __init__(self):
        # human or machine
        self.type_of_driver = "Human"

        # resource related
        self.host = "127.0.0.1"
        self.port = 2000
        self.path = "/scratch/yang/aws_data/carla_collect/exptown_v3_noise5/"  # If path is set go for it , if not expect a name set
        # TODO: make sure path exists

        # data collection related
        self.city_name = 'Exp_Town'
        self.carla_config = None # This will be filled by the caller
        # collect method
        self.autopilot = True
        self.use_planner = True # only useful in carlaHuman, used to randomly walk in the city
        self.noise = "Spike" #"Spike"  # NON CARLA SETTINGS PARAM

        self.reset_period = 960 # reset when the system time goes beyond this number
        # Those parameters will override carla_config
        self.weather = "1" # This will be override by the caller
        self.cars = "50"
        self.pedestrians = "100"
        # TODO: change hash_data_collection
        self.num_images_to_collect = 200*20 * 3 # how many images to collect in total
        self.re_entry = True # True to allow continue collecting the data, this will make changes to the folder structure

        # post processing
        self.image_cut = [0, None]  # This is made from top to botton  # decide to save the full image
        self.resolution = [768, 576]

        # TODO: turn this one to visualize
        # Visualization related
        self.show_screen = False  # NON CARLA SETTINGS PARAM
        self.aspect_ratio = [3, 1]  # only matters when showing the screen
        self.scale_factor = 1  # NON CARLA SETTINGS PARAM
        self.plot_vbp = False
        self.number_screens = 1 # added later

        # others
        self.interface = "Carla" # always fixed

        self.noise_frequency = 45
        self.noise_intensity = 5
        self.min_noise_time_amount = 0.5
        self.no_noise_decay_stage = True
        self.use_tick = True

        if self.city_name == "Exp_Town":
            self.parking_position_file = "town03_intersections/positions_file_Exp_Town.parking.txt"