<<<<<<< HEAD
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    ARRAY,
    JSON,
)
from typing import Optional, Dict, Any, List
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from datetime import datetime
from mangum import Mangum

# from typing import Optional
import os

DATABASE_URL = os.getenv(
    "DB_URL_PROD", "mysql+pymysql://root:lotusde7@localhost:3306/store"
)
ENV = os.getenv("ENV", "prod")  # si no esta definida, asumimos "production"

if ENV == "dev":
    print("Estamos en el ambiente de desarrollo.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)


class OrderProduct(Base):
    __tablename__ = "order_product"
    order_id = Column(Integer, ForeignKey("orders.id"), primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)


class ProductCreateUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    stock: int
    created_at: Optional[datetime] = None


# modeelo pydantic para la creacn/actualisacion de ordenes
class OrderProductCreate(BaseModel):
    product_id: int
    quantity: int
    price: float


class OrderCreateUpdate(BaseModel):
    quantity: int
    price: float
    date: Optional[datetime] = None
    order_products: List[OrderProductCreate]


# crear tablas
Base.metadata.create_all(bind=engine)


# dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()

origins = ["*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/orders/")
def read_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).all()
    return orders


@app.get("/orders/{order_id}")
def read_order(order_id: int, db: Session = Depends(get_db)):
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")

    # obtiene todos los products de del order
    order_products = (
        db.query(OrderProduct).filter(OrderProduct.order_id == order_id).all()
    )

    return {
        "id": db_order.id,
        "quantity": db_order.quantity,
        "price": db_order.price,
        "date": db_order.date,
        "order_products": order_products,
    }


@app.get("/products/")
def read_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return products


@app.delete("/orders/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    # primero borra todos las order products del order
    db.query(OrderProduct).filter(OrderProduct.order_id == order_id).delete()

    # ahora si borra le order
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")

    db.delete(db_order)
    db.commit()
    return {"message": "oRder deleted"}


@app.post("/orders/")
def create_order(order: OrderCreateUpdate, db: Session = Depends(get_db)):
    order_data = order.dict()
    order_data["date"] = datetime.utcnow()
    order_products = order_data.pop("order_products")

    # valida que los priodcutos existan
    product_ids = [product["product_id"] for product in order_products]
    existing_products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    existing_product_ids = {product.id for product in existing_products}

    # verifica que existan
    missing_products = set(product_ids) - existing_product_ids
    if missing_products:
        raise HTTPException(
            status_code=404, detail=f"Products with IDs {missing_products} not found"
        )

    # crea la ordern
    db_order = Order(**order_data)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    # crear cada order product
    created_products = []
    for product in order_products:
        order_product_data = product
        order_product_data["order_id"] = db_order.id
        db_order_product = OrderProduct(**order_product_data)
        db.add(db_order_product)
        created_products.append(db_order_product)

    db.commit()
    for product in created_products:
        db.refresh(product)

    return {
        "id": db_order.id,
        "quantity": db_order.quantity,
        "price": db_order.price,
        "date": db_order.date,
        "order_products": created_products,
    }


@app.put("/orders/{order_id}")
def update_order(
    order_id: int, order: OrderCreateUpdate, db: Session = Depends(get_db)
):
    # actualiza order
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")

    order_data = order.dict()
    order_products = order_data.pop("order_products")

    # Valida que existan los productos
    product_ids = [product["product_id"] for product in order_products]
    existing_products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    existing_product_ids = {product.id for product in existing_products}

    # Checka que existan los proedcutos
    missing_products = set(product_ids) - existing_product_ids
    if missing_products:
        raise HTTPException(
            status_code=404, detail=f"Products with IDs {missing_products} not found"
        )

    # actualiza los aatributos
    for key, value in order_data.items():
        setattr(db_order, key, value)

    # borra prodcutso que existen
    db.query(OrderProduct).filter(OrderProduct.order_id == order_id).delete()

    # crea los productso de nuevo
    created_products = []
    for product in order_products:
        order_product_data = product
        order_product_data["order_id"] = order_id
        db_order_product = OrderProduct(**order_product_data)
        db.add(db_order_product)
        created_products.append(db_order_product)

    db.commit()
    db.refresh(db_order)
    for product in created_products:
        db.refresh(product)

    return {
        "id": db_order.id,
        "quantity": db_order.quantity,
        "price": db_order.price,
        "date": db_order.date,
        "order_products": created_products,
    }


handler = Mangum(app)
=======
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    ARRAY,
    JSON,
)
from typing import Optional, Dict, Any, List
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from datetime import datetime
from mangum import Mangum

# from typing import Optional
import os

DATABASE_URL = os.getenv(
    "DB_URL_PROD", "mysql+pymysql://root:lotusde7@localhost:3306/store"
)
ENV = os.getenv("ENV", "prod")  # si no esta definida, asumimos "production"

if ENV == "dev":
    print("Estamos en el ambiente de desarrollo.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)


class OrderProduct(Base):
    __tablename__ = "order_product"
    order_id = Column(Integer, ForeignKey("orders.id"), primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)


class ProductCreateUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    stock: int
    created_at: Optional[datetime] = None


# modeelo pydantic para la creacn/actualisacion de ordenes
class OrderProductCreate(BaseModel):
    product_id: int
    quantity: int
    price: float


class OrderCreateUpdate(BaseModel):
    quantity: int
    price: float
    date: Optional[datetime] = None
    order_products: List[OrderProductCreate]


# crear tablas
Base.metadata.create_all(bind=engine)


# dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()

origins = ["*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/orders/")
def read_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).all()
    return orders


@app.get("/orders/{order_id}")
def read_order(order_id: int, db: Session = Depends(get_db)):
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")

    # obtiene todos los products de del order
    order_products = (
        db.query(OrderProduct).filter(OrderProduct.order_id == order_id).all()
    )

    return {
        "id": db_order.id,
        "quantity": db_order.quantity,
        "price": db_order.price,
        "date": db_order.date,
        "order_products": order_products,
    }


@app.get("/products/")
def read_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return products


@app.delete("/orders/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    # primero borra todos las order products del order
    db.query(OrderProduct).filter(OrderProduct.order_id == order_id).delete()

    # ahora si borra le order
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")

    db.delete(db_order)
    db.commit()
    return {"message": "oRder deleted"}


@app.post("/orders/")
def create_order(order: OrderCreateUpdate, db: Session = Depends(get_db)):
    order_data = order.dict()
    order_data["date"] = datetime.utcnow()
    order_products = order_data.pop("order_products")

    # valida que los priodcutos existan
    product_ids = [product["product_id"] for product in order_products]
    existing_products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    existing_product_ids = {product.id for product in existing_products}

    # verifica que existan
    missing_products = set(product_ids) - existing_product_ids
    if missing_products:
        raise HTTPException(
            status_code=404, detail=f"Products with IDs {missing_products} not found"
        )

    # crea la ordern
    db_order = Order(**order_data)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    # crear cada order product
    created_products = []
    for product in order_products:
        order_product_data = product
        order_product_data["order_id"] = db_order.id
        db_order_product = OrderProduct(**order_product_data)
        db.add(db_order_product)
        created_products.append(db_order_product)

    db.commit()
    for product in created_products:
        db.refresh(product)

    return {
        "id": db_order.id,
        "quantity": db_order.quantity,
        "price": db_order.price,
        "date": db_order.date,
        "order_products": created_products,
    }


@app.put("/orders/{order_id}")
def update_order(
    order_id: int, order: OrderCreateUpdate, db: Session = Depends(get_db)
):
    # actualiza order
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")

    order_data = order.dict()
    order_products = order_data.pop("order_products")

    # Valida que existan los productos
    product_ids = [product["product_id"] for product in order_products]
    existing_products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    existing_product_ids = {product.id for product in existing_products}

    # Checka que existan los proedcutos
    missing_products = set(product_ids) - existing_product_ids
    if missing_products:
        raise HTTPException(
            status_code=404, detail=f"Products with IDs {missing_products} not found"
        )

    # actualiza los aatributos
    for key, value in order_data.items():
        setattr(db_order, key, value)

    # borra prodcutso que existen
    db.query(OrderProduct).filter(OrderProduct.order_id == order_id).delete()

    # crea los productso de nuevo
    created_products = []
    for product in order_products:
        order_product_data = product
        order_product_data["order_id"] = order_id
        db_order_product = OrderProduct(**order_product_data)
        db.add(db_order_product)
        created_products.append(db_order_product)

    db.commit()
    db.refresh(db_order)
    for product in created_products:
        db.refresh(product)

    return {
        "id": db_order.id,
        "quantity": db_order.quantity,
        "price": db_order.price,
        "date": db_order.date,
        "order_products": created_products,
    }


handler = Mangum(app)
>>>>>>> e93e7bbaa11b1b659af7c0b504251706b21d431e
