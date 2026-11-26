from collections.abc import Iterable

from models.user import UserModel, UserRole


def search_customers(
    users: Iterable[UserModel],
    query: str = "",
) -> list[UserModel]:
    normalized_query = query.strip().casefold()
    customers = (user for user in users if user.role == UserRole.CUSTOMER)
    if not normalized_query:
        return sorted(customers, key=lambda user: user.username.casefold())

    return sorted(
        (
            user
            for user in customers
            if normalized_query in " ".join(
                filter(
                    None,
                    (
                        user.username,
                        user.email or "",
                        user.phone_number,
                        user.user_id,
                    ),
                )
            ).casefold()
        ),
        key=lambda user: user.username.casefold(),
    )
