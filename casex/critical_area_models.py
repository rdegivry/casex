import warnings
import numpy as np
import math

import casex


class CCriticalAreaModels:
    """
    [Explanation of the purpose of this class]
    
    [Quick review of the member functions]
    """

    def __init__(self, buffer: float = 0.3, height: float = 1.8):
        """
        
        Parameters
        ----------          
        buffer : float, optional
            [m] Radius of a standard person as seen from above (default is 0.3 m)
        height : float, optional
            [m] The altitude above the ground at which the aircraft can first impact a person (default is 1.8 m)        
        """

        self.buffer = buffer
        self.height = height

        self._self_test()

    def critical_area(self, critical_area_model: casex.enums.ECriticalAreaModel,
                      aircraft: casex.aircraft_specs.AircraftSpecs, impact_speed: float, impact_angle: float,
                      critical_areas_overlap: float, var1: float = -1):
        """Computes the lethal area as modeled by different models.
        
        The models are described in more detail in SORA Annex F. References for each model is given in the code.
        
        This function supports one of the following input parameters to be a vector, which will give a vector of the same size as output:
            
        * impact_speed
        * impact_angle
        * critical_area_overlap
        * aircraft.width
        * aircraft.length
        * aircraft.fuel_quantity
        
        This vector is given as ``numpy.array``, and only one of the parameters can be a vector for each call. The return values are then also ``numpy.array`` IF the input parameter that is a ``numpy.array`` is used in the computation.

        Parameters
        ----------       
        critical_area_model : :class:`ECriticalAreaModel`
            Choice of model (RCC [5]_, RTI [3]_, FAA [2]_, NAWCAD [7]_, JARUS [1]_). See SORA Annex F for details [1]_.
        aircraft : :class:`CAircraftSpecs`
            Class with information about the aircraft        
        impact_speed : float
            [m/s] Impact speed of aircraft (this is speed along the velocity vector).
        impact_angle : float
            [deg] Impact angle relative to ground (90 is vertical, straight down).
            A value smaller than 
        critical_areas_overlap : float
            [0 to 1] Fraction of overlap between lethal area from glide and from explosion/deflagration.
        var1 : float, optional
            An additional variable that is used in FAA, NAWCAD, and JARUS models.
            For the FAA model, `var1` = :math:`F_A`, the ratio of secondary debris field to primary debris field. If not specified, :math:`F_A` = 4.36 will be used. See [2]_ page 98.
            For the NAWCAD model, `var1` is the lethal kinetic energy threshold in J. If not specified (or set to -1) the value 73.2 J is used.
            For the JARUS model, `var1` is the lethal kinetic energy threshold in J. If not specified (or set to -1), the following is done (see Annex F section A.5 for details): `var1` is set to 290 J, except when the width of the aircraft is <= 1 m, in which case `var1` is set to 2 * 290 J.
        
        Returns
        -------       
        critical area : float
            [m^2] Size of the critical area for the selected model.
        estimated glide area : float
            [m^2] The glide and slide areas are estimated as the relation between the glide and slide distances multiplied by the glide+slide area. The glide area is returned as the second output.
        estimated slide area : float
            [m^2] The estimated slide area is returned as the third output.
        critical area inert : float
            [m^2] The inert part of the critical area.
        deflagration area : float
            [m^2] The deflagration area as given by the deflagration model.
        """

        # Check on input argument validity
        if not isinstance(critical_area_model, casex.enums.ECriticalAreaModel):
            warnings.warn("Critical area model not recognized. Type set to RCC.")
            critical_area_model = casex.enums.ECriticalAreaModel.RCC

        if not isinstance(aircraft, casex.aircraft_specs.AircraftSpecs):
            raise ("Aircraft not recognized. Must be of type CAircraftSpecs")

        # Instantiate necessary classes
        Exp = casex.explosion_models.CExplosionModels()

        # Compute additional parameters
        horizontal_impact_speed = self.horizontal_speed_from_angle(impact_angle, impact_speed)
        glide_distance = self.glide_distance(impact_angle)

        # Compute the inert LA
        if critical_area_model == casex.enums.ECriticalAreaModel.RCC:
            # Slide distance based on friction
            slide_distance_friction = self.slide_distance_friction(horizontal_impact_speed,
                                                                   aircraft.friction_coefficient)
            # [5, p. D-4]
            glide_area = np.multiply(aircraft.length + glide_distance + 2 * self.buffer,
                                     aircraft.width + 2 * self.buffer)
            slide_area = np.multiply(slide_distance_friction, aircraft.width + 2 * self.buffer)

        elif critical_area_model == casex.enums.ECriticalAreaModel.RTI:
            # Slide distance based on friction
            slide_distance_friction = self.slide_distance_friction(
                aircraft.coefficient_of_restitution * horizontal_impact_speed, aircraft.friction_coefficient)
            # [1, p. 6]
            glide_area = 2 * (self.buffer + aircraft.width / 2) * glide_distance + math.pi * np.power(
                self.buffer + aircraft.width / 2, 2)
            slide_area = slide_distance_friction * (2 * self.buffer + aircraft.width)

        elif critical_area_model == casex.enums.ECriticalAreaModel.FAA:
            # [2, p. 99]
            r_D = self.buffer + aircraft.width / 2

            # F_A comes from table 6-5 in [2, p. 98]. Here using the median for 20/80 distribution between hard and
            # soft surfaces
            if var1 == -1:
                F_A = 4.36
            else:
                F_A = var1

            r_Ac = self.buffer + aircraft.width / 2 * np.sqrt(F_A)
            hs = self.height * np.sin(np.deg2rad(90 - impact_angle))
            y2m = np.power(2 * r_Ac * hs, 2) - np.power(np.power(r_Ac, 2) + np.power(hs, 2) - np.power(r_D, 2), 2)

            # If y2m becomes negative, it means that A_C_mark should become zero, because the secondary
            # debris area is larger than the total glide area. This is accomplished by simply setting y2 = 0
            y2m = np.maximum(0, y2m)
            y2 = np.sqrt(y2m) / (2 * hs)

            A_C_mark = 2 * y2 * hs
            A_C_mark = A_C_mark + (
                    y2 * np.sqrt(np.power(r_D, 2) - np.power(y2, 2)) + np.power(r_D, 2) * np.arcsin(y2 / r_D))
            A_C_mark = A_C_mark - (
                    y2 * np.sqrt(np.power(r_Ac, 2) - np.power(y2, 2)) + np.power(r_Ac, 2) * np.arcsin(y2 / r_Ac))

            # Note that this is not identical to (12), since (12) assumes 0 degrees is vertical and not horizontal
            LA_inert = math.pi * np.power(self.buffer + aircraft.width / 2 * np.sqrt(F_A), 2) + A_C_mark

            glide_area = math.pi * np.power(self.buffer + aircraft.width / 2, 2)
            slide_area = LA_inert - glide_area

        elif critical_area_model == casex.enums.ECriticalAreaModel.NAWCAD:
            # All from [7]
            if var1 == -1:
                KE_lethal = casex.conversions.ftlb_to_J(54)
            else:
                KE_lethal = var1

            # P. 18 (the following equation is just KE to mass and velocity, not taken from [7])
            velocity_min_kill = np.sqrt(2 * KE_lethal / aircraft.mass)

            # Intermediate variable
            acceleration = aircraft.friction_coefficient * casex.constants.GRAVITY

            # P. 17
            # This is (15), but it seems to be wrong; normally at = v, not 2at = v
            # t_safe = (horizontal_impact_speed - velocity_min_kill) / 2 / aircraft.friction_coefficient / constants.GRAVITATIONAL
            # This seems to be the correct formula
            t_safe = (horizontal_impact_speed - velocity_min_kill) / acceleration

            # Avoid having negative time
            t_safe = np.maximum(0, t_safe)

            # P. 17
            skid_distance_lethal = (horizontal_impact_speed * t_safe) - (0.5 * acceleration * t_safe * t_safe)

            # P. 25
            glide_area = glide_distance * (2 * self.buffer + aircraft.width)
            slide_area = skid_distance_lethal * (2 * self.buffer + aircraft.width)

        elif critical_area_model == casex.enums.ECriticalAreaModel.JARUS:
            if var1 == -1:
                KE_lethal = 290
                if aircraft.width <= 1:
                    KE_lethal = 290 * 2
            else:
                KE_lethal = var1

            velocity_min_kill = np.sqrt(2 * KE_lethal / aircraft.mass)
            acceleration = aircraft.friction_coefficient * casex.constants.GRAVITY

            t_safe = (aircraft.coefficient_of_restitution * horizontal_impact_speed - velocity_min_kill) / acceleration
            t_safe = np.maximum(0, t_safe)

            slide_distance_lethal = (aircraft.coefficient_of_restitution * horizontal_impact_speed * t_safe) - (
                    0.5 * acceleration * t_safe * t_safe)

            circular_end = math.pi * np.power(self.buffer + aircraft.width / 2, 2)
            glide_area = 2 * (self.buffer + aircraft.width / 2) * glide_distance + circular_end
            slide_area = slide_distance_lethal * (2 * self.buffer + aircraft.width)

        # Add glide and slide from model
        LA_inert = glide_area + slide_area

        # Compute deflagration area based on both fireball and thermal lethal area
        TNT = Exp.TNT_equivalent_mass(aircraft.fuel_type, aircraft.fuel_quantity)
        FB = Exp.fireball_area(TNT)
        p_lethal = 0.1
        TLA = Exp.lethal_area_thermal(TNT, p_lethal)
        LA_deflagration = np.maximum(FB, TLA)

        # Compute the overlapping area between inert and deflagration
        overlapping_area = np.minimum(LA_inert, LA_deflagration) * np.maximum(0, np.minimum(critical_areas_overlap, 1))

        return LA_inert + LA_deflagration - overlapping_area, glide_area, slide_area, LA_inert, LA_deflagration

    def slide_distance_friction(self, velocity, friction_coefficient):
        """Computes slide distance based on initial velocity and friction
        
        Sliding distance computed based on the assumption
            
        .. math:: F = -f\cdot w,
            
        where F is the frictional force, f the frictional coefficient, and w the body weight.
        The slide distance is the length of the slide between impact and the body coming to rest.
        
        This is a standard assumption found in most sources that includes friction.
        See for instance [7]_.
        
        Parameters
        ----------
        
        velocity : float
            [m/s] Horizontal component of the impact velocity
        friction_coefficient : float
            [] Friction coefficient, typical between 0.4 and 0.7
        
        Returns
        -------
        
        distance : float
            [m] Distance from impact to rest
        """
        return velocity * velocity / 2 / friction_coefficient / casex.constants.GRAVITY

    def glide_distance(self, glide_angle: float):
        """Compute glide distance based on glide angle
        
        Glide distance is the distance an aircraft will glide through the air for a given glide angel from altitude Height and until it impact the ground.
        Thus, the glide starts at altitude Height and continues until the aircraft impacts the ground.
        
        Parameters
        ----------
        glide_angle : float, 
            [deg] The angle of the aircraft relative to the ground as is impacts the ground. Must be between 1 and 179 degree. Values above 90 degrees are used as '180 - GlideAngle'.
        
        Returns
        -------
        
        distance : float
            [m] The glide distance
        """
        # Height out of range
        if np.any(self.height < 0):
            warnings.warn("Height in computation of glide distance is less than zero, which does not make sense."
                          " Subsequent computations are not valid.")
            self.height = 0

        # Sanity check on glide angle
        glide_angle = self.check_glide_angle(glide_angle)

        # This is just triangle standard math
        return self.height / np.tan(np.radians(glide_angle))

    def check_glide_angle(self, glide_angle: float):
        """Performs a sanity check on the glide angle
        """
        # glide_angle out of range    
        if np.any(glide_angle < 0) or np.any(glide_angle > 180):
            warnings.warn("glide_angle is out of valid range (0 to 180). Subsequent computations are not valid.")
            glide_angle = np.fromiter(map(lambda x: 90 if (x < 0 or x > 180) else x, glide_angle), dtype=np.float)

        # Flip glide angle
        try:
            if glide_angle > 90:
                glide_angle = 180 - glide_angle
        except:
            glide_angle = np.fromiter(map(lambda x: 180 - x if x > 90 else x, glide_angle), dtype=np.float)

        # If glide_angle is close to zero, we get a division by close to zero, so warn the user
        # Also avoids an division by zero error
        if np.any(glide_angle < 1):
            warnings.warn("glide_angle is very small, and may produce numerically unstable results."
                          " Glide angle has been set to 1 degree.")
            glide_angle = np.fromiter(map(lambda x: 1 if x < 1 else x, glide_angle), dtype=np.float)

        return glide_angle

    def horizontal_speed_from_angle(self, impact_angle: float, impact_speed: float):
        """Compute horizontal speed component for a given impact angle and impact speed
        
        
        """

        # Note that we use .abs, since cosine is negative for angles between 90 and 180
        return np.fabs(np.cos(np.radians(impact_angle))) * impact_speed

    def horizontal_speed_from_ratio(self, glide_ratio: float, impact_speed: float):
        """Compute horizontal speed from glide ratio
        
        """
        return (glide_ratio / np.power(np.power(glide_ratio, 2) + 1, 0.5)) * impact_speed

    def vertical_speed_from_angle(self, impact_angle: float, impact_speed: float):
        """Compute vertical speed from descent angle       
        
        """
        return np.sin(np.radians(impact_angle)) * impact_speed

    def glide_angle_from_glide_ratio(self, glide_ratio: float):
        """Compute glide angle from glide ratio
        
        """
        return np.rad2deg(np.arctan2(1, glide_ratio))

    def speed_from_kinetic_energy(self, KE: float, mass: float):
        """Compute speed from kinetic energy
        """
        return np.sqrt(2 * KE / mass)

    def compute_minimum_CDF(self, obstacle_density: float, width, distance_glide_slide: float, resolution: float,
                            p: float = 0.9):
        """Compute xxx
        """
        x = np.linspace(0, distance_glide_slide, resolution)

        Ac = width * distance_glide_slide

        # Compute the approximated CDF        
        y = 1 - np.power(1 - x / distance_glide_slide, obstacle_density * Ac / 1e6)

        # Probability that there are no obstacles in the CA
        p_none = np.power(1 - Ac / 1e6, obstacle_density)

        if (p < 1 - p_none):
            reduction = 1 - np.power(1 - p / (1 - p_none), 1 / ((obstacle_density / 1e6) * Ac))
            Ac_reduced = Ac * reduction
        else:
            Ac_reduced = Ac

        return y, x, p_none, Ac_reduced

    def compute_Poisson_CDF(self, obstacle_density: float, width: float, distance_glide_slide: float, resolution: float):
        """Compute xxx
        """
        x = np.linspace(0, distance_glide_slide, resolution)

        # Compute the Poisson CDF        
        y = 1 - np.exp(-obstacle_density / 1e6 * width * x)

        p_none = np.exp(-obstacle_density / 1e6 * width * distance_glide_slide)

        return y, x, p_none

    def simulate_minimum_CDF(self, obstacle_density: float, width, distance_glide_slide: float, count: int):
        """ Do a simulation of the reduction of the critical area
        
        Note that since this simulation assumes that the obstacle density is an integer, we go for km as distance unit
        """

        # Just a list of integers to use as indexing in y
        test_range = np.arange(count)

        # Fill the resulting variable with the maximum distance
        y = np.full(count, float(distance_glide_slide))

        num_of_obstacles = int(round(obstacle_density))
        no_obstacles_in_CA = 0

        for k in test_range:
            # Get the object location in meters
            # Uniform distribution in the first dimension
            object_locations = np.random.uniform(0, 1000, size=num_of_obstacles)

            # Pick only the objects that is closer to zero (in the length dimension of the CA) than the length of the CA
            objects_inside_distance = object_locations < distance_glide_slide

            # Pick only the objects that is within the width of the aircraft, relative to a width of 1 km (since the object density unit is km^2)
            # This assumes a uniform distribution in the second dimension
            objects_inside_CA = objects_inside_distance & (np.random.uniform(size=num_of_obstacles) < width / 1000)

            # Pick out the objects that are inside the CA
            x = object_locations[objects_inside_CA]

            # If there are none, just let y[k] keep the original value of full CA length
            if len(x) > 0:
                # Otherwise, use the distance to the first object in the glide/slide path
                y[k] = np.amin(x)
            else:
                no_obstacles_in_CA = no_obstacles_in_CA + 1

        return y, no_obstacles_in_CA