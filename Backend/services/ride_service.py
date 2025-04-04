import random
from models.ride_model import Ride, db
from models.rideHistory_model import RideHistory
from models.favouriteLocation_model import FavoriteLocation
from models.location_model import Location
from models.captainRideHistory_model import CaptainRideHistory
from services.map_service import get_distance_time
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import SQLAlchemyError

def get_fare(pickup, destination):
    """Calculate the fare based on distance and time."""
    # distance, time, path = get_distance_time(pickup, destination)
    result = get_distance_time(pickup, destination)
    distance = float(result["distance"])
    time = float(result["duration"])
    path = result["path"]

    print(f"line 19 - distance: {distance}, duration: {time}, path: {path}")
    if not pickup or not destination:
        raise ValueError("Pickup and destination are required")

    # fare = {"auto": distance*30, "car": distance*50, "moto": distance*15}
    # duration= {"auto": time*20+0.1, "car": time*10+0.2, "moto": time*8}
    distance = float(distance)
    time = float(time)

    fare = {"auto": round(distance * 30, 2), "car": round(distance * 50, 2), "moto": round(distance * 15, 2)}
    duration = {"auto": round(time * 3 + 0.1, 2), "car": round(time * 2 + 0.2, 2), "moto": round(time * 3, 2)}

    return fare, duration, distance

def generate_otp(length=6):
    """Generate a numeric OTP of given length."""
    return str(random.randint(10**(length-1), (10**length)-1))

def create_ride(pickup, destination, vehicleType):
    from socket_handler import socketio
    from models.user_model import User
    from models.grid import places

    """Create a new ride request."""
    user_id = get_jwt_identity()  # Extract user_id from JWT token

    if not all([user_id, pickup, destination, vehicleType]):
        return {"error": "All fields are required"}, 400

    user = User.query.get(user_id)
    if not user:
        return {"error": "Invalid user ID"}, 400

    fare, duration, distance = get_fare(pickup, destination)
    if not fare or vehicleType not in fare:
        return {"error": "Invalid fare data"}, 500
    print(f"line 49 - fare: {fare} \n faretype: {type(fare[vehicleType])}")
    
    print(f"line 38 \n fare: {fare} \n duration: {duration}")

    new_ride = Ride(
        user_id=user_id,
        pickup=pickup,
        destination=destination,
        vehicleType=vehicleType,
        distance=distance,
        otp=generate_otp(),
        fare=fare[vehicleType],
        duration=duration[vehicleType]
    )

    db.session.add(new_ride)
    db.session.commit()

    # Check and add pickup location if not exists
    pickup_location = Location.query.filter_by(location_name=pickup).first()
    if not pickup_location:
        lat, lon = places.get(pickup, [None, None])
        if lat is None or lon is None:
            return {"error": "Invalid pickup location"}, 400
        pickup_location = Location(user_id=user_id, location_name=pickup, latitude=lat, longitude=lon)
        db.session.add(pickup_location)
        db.session.commit()

    # Check and add destination location if not exists
    destination_location = Location.query.filter_by(location_name=destination).first()
    if not destination_location:
        lat, lon = places.get(destination, [None, None])
        if lat is None or lon is None:
            return {"error": "Invalid destination location"}, 400
        destination_location = Location(user_id=user_id, location_name=destination, latitude=lat, longitude=lon)
        db.session.add(destination_location)
        db.session.commit()

    ride_data = {
        "ride_id": new_ride.id,
        "pickup": new_ride.pickup,
        "destination": new_ride.destination,
        "vehicleType": new_ride.vehicleType,
        "fare": new_ride.fare,
        "otp": new_ride.otp,
        "user": {
            "id": user.id,
            "fullname": {
                "firstname": user.firstname,
                "lastname": user.lastname
            },
            "email": user.email
        },
        "duration": new_ride.duration,
        "distance": new_ride.distance,
        "status": new_ride.status
    }
    # socketio.emit("new-ride", ride_data, broadcast=True)
    socketio.emit("new-ride", ride_data, to=None)
    return new_ride

def confirm_ride(ride_id, captain_id):
    from socket_handler import socketio
    # socketio.emit("user-rider", {ride_id,captain_id}, to=None)

    from models.captain_model import Captain
    """Confirm a ride by assigning a captain."""
    ride = Ride.query.get(ride_id)
    if ride.status != "pending":
        return {"message": "Ride is already ongoing", "status":"PickedBySomeone","rideId": ride.id}
    
    if not ride:
        raise ValueError("Ride not found")
    
    captain = Captain.query.get(captain_id)
    if not captain:
        raise ValueError("Captain not found")
    captain.status = "active"

    ride.status = "accepted"
    ride.captain_id = captain_id
    db.session.commit()

    # captain = Captain.query.get(captain_id)

    ride_data = {
        "userId": ride.user_id,
        "rideId": ride.id,
        "status": "ongoing",
        "captain": {"id":captain.id, "firstname": captain.firstname, "lastname": captain.lastname,
                    "vehicle_plate": captain.vehicle_plate, "status": captain.status},
        "pickup": ride.pickup,
        "destination": ride.destination,
        "otp": ride.otp,
        "fare": ride.fare,
        "duration": ride.duration,
        "distance": ride.distance,
        "vehicleType": ride.vehicleType
    }
    
    # socketio.emit("ride-confirmed", ride_data, broadcast=True)  # Emit event to all clients
    socketio.emit("ride-confirmed", ride_data, to=None)
    return ride_data


'''
def confirm_ride(ride_id, captain_id):
    """Confirm a ride by assigning a captain with row-level locking."""
    from socket_handler import socketio
    # socketio.emit("user-rider", {ride_id,captain_id}, to=None)
    from models.captain_model import Captain
    try:
        # Lock the ride row for update
        ride = db.session.query(Ride).with_for_update().get(ride_id)
        print(f'Trying 112 - {captain_id}')
        
        if ride.status != "pending":
            return {"message": "Ride is already ongoing", "status": "PickedBySomeone", "rideId": ride.id}
        
        if not ride:
            raise ValueError("Ride not found")
        
        # Update ride details
        ride.status = "accepted"
        ride.captain_id = captain_id
        db.session.commit()
        print(f"ride commit : 124 - {captain_id}")
        
        captain = Captain.query.get(captain_id)
        
        ride_data = {
            "rideId": ride.id,
            "status": "ongoing",
            "captain": {"captain_id":captain.id,"firstname": captain.firstname, "lastname": captain.lastname,
                        "vehicle_plate": captain.vehicle_plate},
            "pickup": ride.pickup,
            "destination": ride.destination,
            "otp": ride.otp,
            "fare": ride.fare
        }
        
        # Emit event to notify clients
        socketio.emit("ride-confirmed", ride_data, to=None)
        return ride_data
    
    except SQLAlchemyError as e:
        db.session.rollback()
        return {"message": "An error occurred", "status": "Error", "error": str(e)}
'''

'''
def start_ride(ride_id, otp, captain_id):
    from socket_handler import socketio
    from models.captain_model import Captain
    """Start a ride if OTP matches."""
    ride = Ride.query.get(ride_id)
    if not ride:
        raise ValueError("Ride not found")
    
    # if ride.status == "ongoing" or ride.status == "accepted":
    #     return {"message": "Ride is already ongoing", "status":"PickedBySomeone","rideId": ride.id}
    
    if ride.status != "accepted":
        raise ValueError("Ride not accepted")

    if ride.otp != otp:
        raise ValueError("Invalid OTP")

    ride.status = "ongoing"
    db.session.commit()

    captain = Captain.query.get(captain_id)

    ride_data = {
        "rideId": ride.id,
        "status": "ongoing",
        "captain": {"firstname": captain.firstname, "lastname": captain.lastname},
        "destination": ride.destination,
        "fare": ride.fare
    }
    
    # socketio.emit("ride-started", ride_data, broadcast=True)
    socketio.emit("ride-started", ride_data, to=None)
    return ride_data

'''

def start_ride(ride_id, otp, captain_id):
    from socket_handler import socketio
    from models.captain_model import Captain
    """Start a ride if OTP matches."""
    ride = Ride.query.get(ride_id)
    if not ride:
        raise ValueError("Ride not found")

    if ride.status != "accepted":
        raise ValueError("Ride not accepted")

    if ride.otp != otp:
        raise ValueError("Invalid OTP")

    ride.status = "ongoing"
    db.session.commit()

    captain = Captain.query.get(captain_id)

    ride_data = {
        "rideId": ride.id,
        "status": "ongoing",
        "captain": {"id":captain.id, "firstname": captain.firstname, "lastname": captain.lastname},
        "destination": ride.destination,
        "fare": ride.fare,
        "duration": ride.duration,
        "distance": ride.distance,
        "vehicleType": ride.vehicleType,
        "userId": ride.user_id,
    }
    
    # socketio.emit("ride-started", ride_data, broadcast=True)
    socketio.emit("ride-started", ride_data, to=None)
    return ride_data

def end_ride(ride_id, captain_id):
    from socket_handler import socketio
    """Complete a ride."""
    print(ride_id, captain_id)
    ride = Ride.query.filter_by(id=ride_id, captain_id=captain_id).first()
    if not ride:
        raise ValueError("Ride not found")

    if ride.status != "ongoing":
        raise ValueError("Ride not ongoing")

    ride.status = "completed"
    db.session.commit()

    ride_history_entry = RideHistory(
        user_id=ride.user_id,
        ride_id=ride.id,
        pickup=ride.pickup,
        destination=ride.destination,
        fare=ride.fare,
        status=ride.status
    )
    db.session.add(ride_history_entry)
    db.session.commit()

    captain_ride_history_entry = CaptainRideHistory(
        captain_id=captain_id,
        ride_id=ride.id,
        pickup=ride.pickup,
        destination=ride.destination,
        status=ride.status
    )
    db.session.add(captain_ride_history_entry)
    db.session.commit()

    favorite = FavoriteLocation.query.filter_by(
        user_id=ride.user_id, pickup=ride.pickup, destination=ride.destination
    ).first()

    if favorite:
        favorite.count += 1  # Increase count if the route is frequently used
    else:
        new_favorite = FavoriteLocation(user_id=ride.user_id, ride_id=ride.id, 
                                        pickup=ride.pickup, destination=ride.destination)
        db.session.add(new_favorite)

    db.session.commit()

    ride_data = {"rideId": ride.id, "status": ride.status}

    # socketio.emit("ride-ended", ride_data, broadcast=True)  # Ensure correct data format
    socketio.emit("ride-ended", ride_data, to=None)
    return ride
