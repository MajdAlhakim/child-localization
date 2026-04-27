package qa.qu.trakn.parentapp.data.api

import okhttp3.ResponseBody
import qa.qu.trakn.parentapp.data.models.GetApsResponse
import qa.qu.trakn.parentapp.data.models.HealthResponse
import qa.qu.trakn.parentapp.data.models.TagsResponse
import qa.qu.trakn.parentapp.data.models.VenuesResponse
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Path

interface ApiService {

    @GET("/health")
    suspend fun health(): HealthResponse

    @GET("/api/v1/venues")
    suspend fun getVenues(): VenuesResponse

    @GET("/api/v1/floor-plans/{fpId}/image")
    suspend fun getFloorPlanImage(
        @Path("fpId") fpId: String,
    ): Response<ResponseBody>

    @GET("/api/v1/floor-plans/{fpId}/aps")
    suspend fun getFloorPlanAps(
        @Path("fpId") fpId: String,
        @Header("X-API-Key") apiKey: String,
    ): GetApsResponse

    @GET("/api/v1/tags")
    suspend fun getTags(
        @Header("X-API-Key") apiKey: String,
    ): TagsResponse
}
